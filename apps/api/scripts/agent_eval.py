"""Agent 评测脚本：用固定用例跑「事实 → prompt → 模型 → 护栏」全链路。

与线上链路保持一致的三点（因此评测结果可迁移到真实请求）：
1. 事实先过 ``policies.scrub``，与 ``tools`` 层脱敏完全同一份实现；
2. 急症关键词命中直接短路返回固定指引，不调模型（对应图的 redline 节点）；
3. 模型输出一律经 ``policies`` 解析与后置校验，不由脚本另写一套判断。

用例数据在 ``tests/agent_eval/cases.json``，与 ``OrderFacts`` 字段对齐；
改 prompt 版本号或换模型时，用它对比质量、延迟与护栏命中情况。

用法：
    .venv/bin/python scripts/agent_eval.py                     # 跑全部用例
    .venv/bin/python scripts/agent_eval.py --suite record --limit 3
    .venv/bin/python scripts/agent_eval.py --suite chat        # 只跑员工对话
    .venv/bin/python scripts/agent_eval.py --provider mock     # 离线回归
    .venv/bin/python scripts/agent_eval.py --json /tmp/eval.json

套件：record（记录润色）/ prep（服务前提示）/ dispatch（派单解释）/
      task（异常解释）/ chat（这单助手）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# sys.path 先注入项目根，下面的 import 才能生效
from app.core.config import settings
from app.modules.agents import policies, prompts
from app.modules.agents.models import build_chat_model

# 对话场景的模型开关与线上同源：漏关 json_mode 会让回答变成一串空格，
# 这类问题 mock 永远测不出来，评测集必须跟着真实链路走
from app.modules.agents.scenarios.chat import _CHAT_MODEL_KWARGS
from app.modules.agents.tools import OrderFacts

CASES_FILE = Path(__file__).resolve().parents[1] / "tests" / "agent_eval" / "cases.json"
_PHONE_RE = re.compile(r"\d{11}")
# mock 模式标记：由 main 按 provider 设置，供 _report 区分「回归失败」与「mock 无意义断言」
_SMOKE = False


def _load_cases(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


def _facts(raw: dict[str, Any]) -> OrderFacts:
    """构造事实并脱敏：真实链路在 tools 层完成，这里必须保持同一行为。"""
    facts = OrderFacts(**raw)
    return replace(
        facts,
        health_notes=policies.scrub(facts.health_notes),
        order_notes=policies.scrub(facts.order_notes),
    )


def _facts_text(facts: dict[str, Any]) -> str:
    """护栏做数字比对的序列化口径，与 ``scenarios/*`` 内保持一致。"""
    return json.dumps(facts, ensure_ascii=False, sort_keys=True, default=str)


def _invoke(model, messages, **kwargs: Any) -> tuple[str, int]:
    """调模型并返回 ``(文本, 墙钟耗时毫秒)``；异常交给调用方判定失败。"""
    started = time.perf_counter()
    response = model.invoke(messages, **kwargs)
    elapsed = int((time.perf_counter() - started) * 1000)
    return str(response.content or ""), elapsed


def _report(case_id: str, passed: bool, detail: str, elapsed: int) -> dict[str, Any]:
    """记一条结果。

    mock 下模型只会回一段固定 JSON，内容断言必然大面积不成立（不是回归）：
    这类只记冒烟，验证的是链路不崩、护栏能解析，不计入通过率。
    """
    if not passed and _SMOKE:
        print(f"[SMOKE] {case_id:<13} {elapsed:>6}ms  {detail}")
        return {
            "id": case_id,
            "passed": False,
            "skipped": True,
            "detail": detail,
            "latency_ms": elapsed,
        }
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {case_id:<14} {elapsed:>6}ms  {detail}")
    return {"id": case_id, "passed": passed, "detail": detail, "latency_ms": elapsed}


def run_record_case(model, case: dict[str, Any]) -> dict[str, Any]:
    """记录代写：急症短路 → 生成 → 解析 → 结构/隐私校验。"""
    facts = _facts(case["facts"])
    expect = case.get("expect") or {}
    notes = case["notes"]

    if policies.hit_redline(notes):
        content = policies.REDLINE_REPLY
        passed = bool(expect.get("redline")) and content == policies.REDLINE_REPLY
        return _report(case["id"], passed, "急症短路，未调用模型", 0)

    messages = prompts.record_draft_messages(
        facts.to_prompt_dict(), notes, case.get("photo_count", 0)
    )
    try:
        raw, elapsed = _invoke(model, messages)
    except Exception as exc:  # noqa: BLE001 - 评测脚本需把任何失败记成一条用例失败
        return _report(case["id"], False, f"模型调用失败：{exc}", 0)

    payload = policies.parse_json_object(raw)
    content, prep_brief, warnings = policies.guard_record_output(payload)

    problems: list[str] = []
    if payload is None:
        problems.append("JSON 解析失败")
    if not content:
        problems.append("内容为空")
    if expect.get("sections"):
        missing = [s.rstrip("：") for s in policies.REQUIRED_SECTIONS if s not in content]
        if missing:
            problems.append("缺段：" + "/".join(missing))
    if len(prep_brief) < int(expect.get("min_prep_items", 0)):
        problems.append(f"提示不足 {len(prep_brief)} 条")
    if expect.get("no_pii"):
        # 档案里的手机号与门牌必须已被 scrub 掉，模型也不可能复述出来
        if _PHONE_RE.search(json.dumps(facts.to_prompt_dict(), ensure_ascii=False)):
            problems.append("事实未脱敏")
        if _PHONE_RE.search(content) or "3 栋" in content:
            problems.append("输出复述了隐私")
    for word in expect.get("forbid") or []:
        # 润色的核心约束：原文没提的病情/用药不许凭档案补进去
        if word in content:
            problems.append(f"多了不该有的「{word}」")
    must_any = expect.get("require_any") or []
    if must_any and not any(word in content for word in must_any):
        problems.append("丢了原文里的关键信息")
    max_chars = int(expect.get("max_chars") or 0)
    if max_chars and len(content) > max_chars:
        problems.append(f"超长 {len(content)} 字")

    detail = f"内容 {len(content)} 字，提示 {len(prep_brief)} 条"
    if warnings:
        detail += "，警告 " + ",".join(warnings)
    if problems:
        detail += "；问题：" + "，".join(problems)
    return _report(case["id"], not problems, detail, elapsed)


def run_prep_case(model, case: dict[str, Any]) -> dict[str, Any]:
    """服务前提示：空档案短路 → 生成 → 条数/长度校验。"""
    facts = _facts(case["facts"])
    expect = case.get("expect") or {}

    if not facts.has_health_info:
        passed = bool(expect.get("short_circuit"))
        return _report(case["id"], passed, "档案无健康信息，短路返回空提示", 0)

    messages = prompts.prep_brief_messages(facts.to_prompt_dict())
    try:
        raw, elapsed = _invoke(model, messages)
    except Exception as exc:  # noqa: BLE001 - 与记录用例一致，失败只记用例失败
        return _report(case["id"], False, f"模型调用失败：{exc}", 0)

    items, warnings = policies.guard_prep_output(policies.parse_json_object(raw))
    low = int(expect.get("min_items", 2))
    high = int(expect.get("max_items", 5))
    problems: list[str] = []
    if not low <= len(items) <= high:
        problems.append(f"条数 {len(items)} 不在 {low}-{high}")
    detail = f"提示 {len(items)} 条"
    if warnings:
        detail += "，警告 " + ",".join(warnings)
    if problems:
        detail += "；问题：" + "，".join(problems)
    return _report(case["id"], not problems, detail, elapsed)


def run_dispatch_case(model, case: dict[str, Any]) -> dict[str, Any]:
    """派单解释：人选与数据缺口以规则为准，模型只负责讲理由。"""
    facts = case["facts"]
    expect = case.get("expect") or {}
    candidates = list(facts.get("candidates") or [])
    if not candidates:
        return _report(case["id"], False, "用例缺 candidates", 0)

    try:
        raw, elapsed = _invoke(
            model,
            prompts.dispatch_suggest_messages(facts),
            max_tokens=settings.agent_dispatch_max_tokens,
        )
    except Exception as exc:  # noqa: BLE001 - 与其他套件一致，失败记一条用例
        return _report(case["id"], False, f"模型调用失败：{exc}", 0)

    payload = policies.parse_json_object(raw)
    result, warnings = policies.guard_dispatch_output(
        payload,
        candidates=candidates,
        rule_gaps=list(facts.get("data_gaps") or []),
        facts_text=_facts_text(facts),
    )

    problems: list[str] = []
    if payload is None:
        problems.append("JSON 解析失败")
    # 护栏只会返回规则第一名或 None：返回 None 就等于这次解释整体作废
    if result.get("staff_id") != int(candidates[0]["staff_id"]):
        problems.append("人选被护栏否决")
    if len(result.get("why") or []) < int(expect.get("min_why", 0)):
        problems.append(f"理由不足 {len(result.get('why') or [])} 条")
    if int(expect.get("min_risks") or 0) > len(result.get("risks") or []):
        problems.append("风险提示缺失")
    if bool(expect.get("alternatives")) != bool(result.get("alternatives")):
        problems.append("备选与候选人数不符")
    if int(expect.get("min_alternatives") or 0) > len(result.get("alternatives") or []):
        problems.append(f"备选不足 {len(result.get('alternatives') or [])} 条")
    if result.get("data_gaps") != list(facts.get("data_gaps") or []):
        problems.append("数据缺口与规则不一致")

    detail = f"理由 {len(result.get('why') or [])} 条，风险 {len(result.get('risks') or [])} 条"
    if warnings:
        detail += "，警告 " + ",".join(warnings)
    if problems:
        detail += "；问题：" + "，".join(problems)
    return _report(case["id"], not problems, detail, elapsed)


def run_task_case(model, case: dict[str, Any]) -> dict[str, Any]:
    """异常解释：动作白名单与升级判定由代码兜底，评测看是否被退回规则。"""
    facts = case["facts"]
    expect = case.get("expect") or {}
    task = facts.get("task") or {}
    detail = facts.get("detail") or {}

    try:
        raw, elapsed = _invoke(
            model,
            prompts.task_explain_messages(facts),
            max_tokens=settings.agent_task_max_tokens,
        )
    except Exception as exc:  # noqa: BLE001
        return _report(case["id"], False, f"模型调用失败：{exc}", 0)

    payload = policies.parse_json_object(raw)
    result, warnings = policies.guard_task_output(
        payload,
        rule_why=str(detail.get("why") or ""),
        rule_suggest=str(detail.get("suggest") or ""),
        severity=str(task.get("severity") or ""),
        elapsed_minutes=int(detail.get("elapsed_minutes") or 0),
        threshold_minutes=int(detail.get("threshold_minutes") or 0),
        facts_text=_facts_text(facts),
    )

    problems: list[str] = []
    if payload is None:
        problems.append("JSON 解析失败")
    if not result.get("what_happened") or not result.get("why"):
        problems.append("解释为空")
    if len(result.get("next_actions") or []) < int(expect.get("min_actions", 1)):
        problems.append("没有可执行的下一步")
    if expect.get("escalate") is not None and bool(result.get("escalate")) != bool(
        expect["escalate"]
    ):
        problems.append("升级判定与规则不一致")

    detail_text = f"动作 {len(result.get('next_actions') or [])} 条，升级={result.get('escalate')}"
    if warnings:
        detail_text += "，警告 " + ",".join(warnings)
    if problems:
        detail_text += "；问题：" + "，".join(problems)
    return _report(case["id"], not problems, detail_text, elapsed)


def run_chat_case(model, case: dict[str, Any]) -> dict[str, Any]:
    """员工对话：事实最小化、说人话；急症与越界必须先短路。"""
    facts = case["facts"]
    question = case["question"]
    expect = case.get("expect") or {}

    short = policies.chat_short_circuit(question)
    if short is not None:
        warning, _reply = short
        passed = bool(expect.get("short_circuit"))
        return _report(case["id"], passed, f"短路（{warning}），未调用模型", 0)
    if expect.get("short_circuit"):
        return _report(case["id"], False, "该短路却没命中", 0)

    try:
        raw, elapsed = _invoke(
            model,
            prompts.chat_messages(facts, history=[], question=question),
            max_tokens=settings.agent_chat_max_tokens,
            **_CHAT_MODEL_KWARGS,
        )
    except Exception as exc:  # noqa: BLE001
        return _report(case["id"], False, f"模型调用失败：{exc}", 0)

    answer, warnings = policies.guard_chat_text(raw, facts_text=_facts_text(facts))
    if not answer:
        # 空回答是最高危的信号：json_mode / 思考模式配错时，模型只会回空格
        return _report(case["id"], False, f"回答为空（原始 {len(raw)} 字符）", elapsed)
    if "facts" in raw.lower() and "facts" not in answer.lower():
        # 模型说了内部字段名，被护栏拦下了：不算失败，但要看趋势
        warnings.append("internal_term_scrubbed")

    problems: list[str] = []
    lowered = answer.lower()
    for word in expect.get("forbid") or []:
        if word.lower() in lowered:
            problems.append(f"多了不该有的「{word}」")
    for word in expect.get("must_include") or []:
        if word not in answer:
            problems.append(f"缺少「{word}」")

    detail = f"{len(answer)} 字：{answer[:36]}"
    if warnings:
        detail += "，警告 " + ",".join(warnings)
    if problems:
        detail += "；问题：" + "，".join(problems)
    # mock 回的是固定 JSON，句子级判断没有意义，一律记冒烟
    return _report(case["id"], not problems and not _SMOKE, detail, elapsed)


def _limit(cases: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    return cases[:limit] if limit else cases


def main() -> int:
    global _SMOKE

    parser = argparse.ArgumentParser(description="Run agent eval cases.")
    parser.add_argument(
        "--suite",
        choices=("record", "prep", "dispatch", "task", "chat", "all"),
        default="all",
    )
    parser.add_argument("--limit", type=int, default=None, help="每个套件最多跑几条")
    parser.add_argument("--file", type=Path, default=CASES_FILE, help="用例文件路径")
    parser.add_argument("--json", type=Path, default=None, help="把结构化结果写到文件")
    parser.add_argument("--provider", choices=("mock", "openai_compatible"), default=None)
    parser.add_argument("--model", default=None, help="覆盖 LLM_MODEL")
    args = parser.parse_args()

    if args.provider:
        settings.llm_provider = args.provider
    if args.model:
        settings.llm_model = args.model
    if args.provider or args.model:
        # build_chat_model 带 lru_cache，覆盖配置后必须清掉旧实例
        build_chat_model.cache_clear()
    model = build_chat_model()

    data = _load_cases(args.file)
    results: list[dict[str, Any]] = []
    _SMOKE = settings.llm_provider == "mock"
    print(f"模型：{model.model_name}  provider={settings.llm_provider}")

    def collect(runner, cases: list[dict[str, Any]]) -> None:
        """跑一个套件；mock 下内容不匹配会由 _report 降级成冒烟。"""
        for case in _limit(cases, args.limit):
            results.append(runner(model, case))

    if args.suite in ("record", "all"):
        print("--- 记录代写 ---")
        collect(run_record_case, data.get("record_draft", []))
    if args.suite in ("prep", "all"):
        print("--- 服务前提示 ---")
        collect(run_prep_case, data.get("prep_brief", []))
    if args.suite in ("dispatch", "all"):
        print("--- 派单解释 ---")
        collect(run_dispatch_case, data.get("dispatch_suggest", []))
    if args.suite in ("task", "all"):
        print("--- 异常解释 ---")
        collect(run_task_case, data.get("task_explain", []))
    if args.suite in ("chat", "all"):
        print("--- 这单助手 ---")
        collect(run_chat_case, data.get("chat", []))

    judged = [item for item in results if not item.get("skipped")]
    passed = sum(1 for item in judged if item["passed"])
    called = [item["latency_ms"] for item in judged if item["latency_ms"] > 0]
    avg = int(sum(called) / len(called)) if called else 0
    print(
        f"\n合计 {len(results)} 条：通过 {passed}，失败 {len(judged) - passed}，"
        f"跳过 {len(results) - len(judged)}，平均延迟 {avg}ms"
    )

    if args.json:
        args.json.write_text(
            json.dumps(
                {"model": model.model_name, "results": results}, ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        print(f"结构化结果已写入 {args.json}")
    return 0 if passed == len(judged) else 1


if __name__ == "__main__":
    raise SystemExit(main())
