"""输出侧规则：脱敏、急症红线、结构校验与医疗措辞后置检查。

这一层刻意放在图内、纯函数、无 I/O：
- 模型说什么不由我们控制，但「什么能出现在记录里」必须由代码决定；
- 同样一组规则在阶段七的对话里复用（回答同样不许给医疗建议）。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

# 手机号 / 身份证 / 门牌：这些信息对生成记录没有价值，且属于隐私，统一在入库前抹掉
_PHONE_RE = re.compile(r"1[3-9]\d{9}")
_ID_CARD_RE = re.compile(r"\d{17}[\dXx]")
_DOOR_RE = re.compile(r"\d+\s*(?:号楼|栋|单元|室|门牌)")

# 急症信号：命中直接返回固定指引，完全不让模型参与，避免延误
REDLINE_KEYWORDS = (
    "胸痛",
    "胸闷",
    "呼吸困难",
    "喘不上气",
    "晕倒",
    "昏迷",
    "意识不清",
    "大出血",
    "出血不止",
    "摔倒动不了",
    "抽搐",
    "中风",
    "口角歪斜",
)

REDLINE_WARNING = "redline"

# 急症场景的固定记录：只写处置与待确认，不做任何病情判断
REDLINE_REPLY = (
    "服务内容：服务过程中老人出现急症相关描述，已按应急流程处理。\n"
    "老人状态：需立即确认老人当前状况，必要时拨打 120 并同步家属与站点。\n"
    "异常与风险：本条由系统安全规则生成，紧急情况请以线下处置与专业医护意见为准。\n"
    "下次安排：待家属与站点确认后补充。\n"
    "照片：未提及。"
)

# 只拦截「让 AI 替医生下医嘱」的措辞；客观转述「医生说继续服药」不在此列
_MEDICAL_ADVICE_RE = re.compile(
    r"(建议|应当|应该|需要|可以|推荐)\s*(停药|停用|减量|加量|换药|改用|自行购药|加服)"
)

REQUIRED_SECTIONS = ("服务内容：", "老人状态：", "异常与风险：", "下次安排：", "照片：")

# 管理端解释场景：动作必须可枚举，前端才能把它映射成真实按钮
ALLOWED_TASK_ACTIONS: dict[str, str] = {
    "call_staff": "联系服务人员",
    "reassign": "改派其他员工",
    "contact_family": "联系家属",
    "collect_balance": "催结尾款",
    "add_record": "补录服务记录",
    "manual_check": "人工核查订单",
}

# 不允许承诺结果：模型一旦写「保证」，管理员可能据此跳过核对
_PROMISE_RE = re.compile(r"保证|一定|肯定能|百分之百|绝对不会")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
# 急救/报警号码是常识，不是模型编的事实：出现它们不应触发「数字以订单为准」
_SAFE_NUMBERS = {"110", "119", "120"}


def scrub(text: str) -> str:
    """去掉手机号、身份证与门牌号；保留其余语义供模型理解。"""
    if not text:
        return ""
    cleaned = _PHONE_RE.sub("***", text)
    cleaned = _ID_CARD_RE.sub("***", cleaned)
    cleaned = _DOOR_RE.sub("***", cleaned)
    return cleaned.strip()


def hit_redline(text: str) -> bool:
    """是否命中急症关键词；宁可在少量正常描述上误判，也不能漏掉急症。"""
    return any(keyword in text for keyword in REDLINE_KEYWORDS)


def parse_json_object(text: str) -> dict[str, Any] | None:
    """从模型输出中提取第一个 JSON 对象。

    兼容三种常见情况：纯 JSON、```json 代码块、JSON 前后带解释文字。
    解析失败返回 None，由调用方降级，不抛异常打断整个请求。
    """
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    if start < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _split_sentences(text: str) -> list[str]:
    """按中英文句读切句，供医疗措辞摘除使用（保留分隔符）。"""
    parts = re.split(r"(?<=[。！？；\n])", text)
    return [part for part in parts if part]


def _drop_medical_advice(text: str) -> tuple[str, bool]:
    sentences = _split_sentences(text)
    kept = [sentence for sentence in sentences if not _MEDICAL_ADVICE_RE.search(sentence)]
    return "".join(kept).strip(), len(kept) != len(sentences)


def guard_record_output(
    payload: dict[str, Any] | None, *, max_chars: int = 800
) -> tuple[str, list[str], list[str]]:
    """校验记录草稿。

    返回 ``(content, prep_brief, warnings)``；解析失败时降级为空内容 + 警告，
    由前端提示员工手工补充，而不是把模型的原始噪音直接塞进输入框。
    """
    warnings: list[str] = []
    if payload is None:
        return "", [], ["bad_output"]

    content = str(payload.get("content") or "").strip()
    if not content:
        return "", [], ["empty_content"]

    if len(content) > max_chars:
        content = content[:max_chars].rstrip()
        warnings.append("truncated")

    content, dropped = _drop_medical_advice(content)
    if dropped:
        # 模型越界给了用药建议：该句必须删掉，不能只提示
        warnings.append("medical_guard")

    missing = [section for section in REQUIRED_SECTIONS if section not in content]
    warnings.extend(f"missing_section:{section.rstrip('：')}" for section in missing)

    raw_items = payload.get("prep_brief") or []
    prep_brief, item_warnings = guard_prep_brief(raw_items, min_items=0)
    warnings.extend(item_warnings)
    return content, prep_brief, warnings


def guard_prep_brief(
    raw_items: Any, *, min_items: int = 2, max_items: int = 5
) -> tuple[list[str], list[str]]:
    """规范化提示条目：去空、去重、限长、限条数。"""
    warnings: list[str] = []
    if not isinstance(raw_items, list):
        return [], ["bad_items"]

    items: list[str] = []
    for raw in raw_items:
        item = str(raw or "").strip()
        if not item or item in items:
            continue
        if len(item) > 40:
            item = item[:40].rstrip()
            warnings.append("item_truncated")
        items.append(item)

    if len(items) > max_items:
        items = items[:max_items]
        warnings.append("too_many_items")
    if len(items) < min_items:
        warnings.append("too_few_items")
    return items, warnings


def guard_prep_output(payload: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    """服务前提示的解析入口：兼容 ``items`` 与 ``prep_brief`` 两种键名。"""
    if payload is None:
        return [], ["bad_output"]
    raw = payload.get("items")
    if raw is None:
        raw = payload.get("prep_brief")
    return guard_prep_brief(raw)


# ------------------------------------------- 管理端解释场景（阶段六）

def facts_hash(facts: dict[str, Any]) -> str:
    """事实指纹：用于缓存命中判断；只存摘要，不存原文。"""
    packed = json.dumps(facts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()


def scrub_tree(value: Any) -> Any:
    """递归脱敏：任务详情是嵌套字典，手机号/门牌可能在任意一层。"""
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {key: scrub_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub_tree(item) for item in value]
    return value


def _clean_item(raw: Any, *, limit: int = 40) -> str:
    """单条解释文本的通用清洗：脱敏 → 去医疗建议 → 去承诺词 → 限长。"""
    text = scrub(str(raw or "")).strip()
    if not text:
        return ""
    sentences = _split_sentences(text)
    kept = [
        sentence
        for sentence in sentences
        if not _MEDICAL_ADVICE_RE.search(sentence) and not _PROMISE_RE.search(sentence)
    ]
    return "".join(kept).strip()[:limit].rstrip()


def _numbers_ok(text: str, source_text: str) -> bool:
    """解释里出现的数字必须在事实里出现，避免模型凭空编时间、金额或人数。"""
    numbers = set(_NUMBER_RE.findall(text)) - _SAFE_NUMBERS
    return numbers <= set(_NUMBER_RE.findall(source_text))


def _clean_list(
    raw: Any, *, limit: int, max_items: int, facts_text: str
) -> tuple[list[str], list[str]]:
    """清洗解释里的列表项：去空、去重、去编造数字、限条数与长度。"""
    warnings: list[str] = []
    if not isinstance(raw, list):
        return [], warnings

    items: list[str] = []
    for value in raw:
        item = _clean_item(value, limit=limit)
        if not item or item in items:
            continue
        if not _numbers_ok(item, facts_text):
            # 数字对不上说明模型在编，整条丢弃比保留更安全
            warnings.append("number_not_in_facts")
            continue
        items.append(item)
        if len(items) >= max_items:
            break
    return items, warnings


def guard_dispatch_output(
    payload: dict[str, Any] | None,
    *,
    candidates: list[dict[str, Any]],
    rule_gaps: list[str],
    facts_text: str,
) -> tuple[dict[str, Any], list[str]]:
    """校验派单解释输出。

    ``staff_id`` 必须落在候选名单内；数据缺口以规则结果为准（不信任模型）。
    任一关键项不满足就返回 ``staff_id=None``，由服务层整单回退到规则文案，
    避免出现「解释说的是 A、按钮却派给 B」这种危险错位。
    """
    warnings: list[str] = []
    by_id = {int(item["staff_id"]): item for item in candidates}
    if payload is None:
        return {"staff_id": None}, ["bad_output"]

    try:
        staff_id = int(payload.get("staff_id"))
    except (TypeError, ValueError):
        # 离线替身（mock）与偶发的漏字段：默认取规则第一名，不因此浪费一次调用
        staff_id = int(candidates[0]["staff_id"])
        warnings.append("staff_id_defaulted")
    if staff_id not in by_id:
        return {"staff_id": None}, ["staff_id_invalid"]
    if staff_id != int(candidates[0]["staff_id"]):
        # 排序由规则决定：模型改人选属于越界，整份回退，避免解释与推荐错位
        return {"staff_id": None}, ["staff_conflict"]

    summary = _clean_item(payload.get("summary"), limit=40)
    if not summary or not _numbers_ok(summary, facts_text):
        return {"staff_id": None}, ["summary_invalid"]

    why, why_warnings = _clean_list(
        payload.get("why"), limit=40, max_items=3, facts_text=facts_text
    )
    warnings.extend(why_warnings)
    if not why:
        return {"staff_id": None}, ["why_missing"]

    risks, risk_warnings = _clean_list(
        payload.get("risks"), limit=40, max_items=3, facts_text=facts_text
    )
    warnings.extend(risk_warnings)

    alternatives: list[dict[str, Any]] = []
    raw_alternatives = payload.get("alternatives")
    if isinstance(raw_alternatives, list) and len(by_id) > 1:
        for raw in raw_alternatives[:3]:
            if not isinstance(raw, dict):
                continue
            try:
                alt_id = int(raw.get("staff_id"))
            except (TypeError, ValueError):
                continue
            if alt_id == staff_id or alt_id not in by_id:
                continue
            note = _clean_item(raw.get("note"), limit=25)
            if not note or not _numbers_ok(note, facts_text):
                continue
            alternatives.append(
                {
                    "staff_id": alt_id,
                    # 姓名以候选名单为准，不采信模型写的名字
                    "name": str(by_id[alt_id].get("name") or ""),
                    "note": note,
                }
            )
            if len(alternatives) >= 2:
                break

    return (
        {
            "staff_id": staff_id,
            "summary": summary,
            "why": why,
            "risks": risks,
            # 数据缺口是硬约束：模型漏写就用规则补齐，模型多写的一律丢弃
            "data_gaps": list(rule_gaps),
            "alternatives": alternatives,
        },
        warnings,
    )


def guard_task_output(
    payload: dict[str, Any] | None,
    *,
    rule_why: str,
    rule_suggest: str,
    severity: str,
    elapsed_minutes: int,
    threshold_minutes: int,
    facts_text: str,
) -> tuple[dict[str, Any], list[str]]:
    """校验异常解释输出：动作必须白名单，升级判定由代码二次覆盖。"""
    warnings: list[str] = []
    if payload is None:
        return {}, ["bad_output"]

    what_happened = _clean_item(payload.get("what_happened"), limit=60)
    if not what_happened or not _numbers_ok(what_happened, facts_text):
        what_happened = _clean_item(rule_why, limit=60)
        warnings.append("what_happened_fallback")

    why = _clean_item(payload.get("why"), limit=40) or _clean_item(rule_why, limit=40)

    actions: list[dict[str, str]] = []
    raw_actions = payload.get("next_actions")
    if isinstance(raw_actions, list):
        for raw in raw_actions[:3]:
            if not isinstance(raw, dict):
                continue
            action = str(raw.get("action") or "").strip()
            if action not in ALLOWED_TASK_ACTIONS:
                warnings.append("action_not_allowed")
                continue
            label = _clean_item(raw.get("label"), limit=20) or ALLOWED_TASK_ACTIONS[action]
            actions.append({"action": action, "label": label})
    if not actions:
        # 没有合法动作时退回规则建议，保证前端永远有可点的一步
        actions = [
            {
                "action": "manual_check",
                "label": _clean_item(rule_suggest, limit=20) or ALLOWED_TASK_ACTIONS["manual_check"],
            }
        ]
        warnings.append("actions_fallback")

    data_gaps, gap_warnings = _clean_list(
        payload.get("data_gaps"), limit=40, max_items=3, facts_text=facts_text
    )
    warnings.extend(gap_warnings)

    escalate = bool(payload.get("escalate"))
    # 高优先级且超过两倍阈值必须升级：这条不采信模型，由代码兜底
    if severity == "high" and threshold_minutes > 0 and elapsed_minutes > threshold_minutes * 2:
        escalate = True

    return (
        {
            "what_happened": what_happened,
            "why": why,
            "next_actions": actions,
            "escalate": escalate,
            "data_gaps": data_gaps,
        },
        warnings,
    )


# ------------------------------------------- 员工「这单助手」（阶段七）

# 意图只用关键词分流：它决定「带哪些事实」与「要不要直接兜底」，
# 判断错了最多是多带一段事实，不会产生错误动作，所以不值得为它多花一次模型调用。
CHAT_INTENT_ORDER = "order"
CHAT_INTENT_ELDER = "elder"
CHAT_INTENT_FLOW = "flow"
CHAT_INTENT_OUT_OF_SCOPE = "out_of_scope"
CHAT_INTENTS = (
    CHAT_INTENT_ORDER,
    CHAT_INTENT_ELDER,
    CHAT_INTENT_FLOW,
    CHAT_INTENT_OUT_OF_SCOPE,
)

# 钱、改派、投诉一律不解释：这些涉及他人权益与责任划分，必须由站点管家处理
_SCOPE_BLOCKERS = (
    "退款",
    "退钱",
    "改价",
    "价格",
    "多少钱",
    "费用",
    "催款",
    "欠费",
    "改派",
    "换人",
    "投诉",
    "赔偿",
    "工资",
    "结算",
)
_FLOW_KEYWORDS = (
    "记录",
    "怎么写",
    "填写",
    "照片",
    "上传",
    "提交",
    "打卡",
    "签到",
    "完成订单",
    "下一步",
    "怎么操作",
    "按钮",
)
_ELDER_KEYWORDS = (
    "老人",
    "阿姨",
    "叔叔",
    "爷爷",
    "奶奶",
    "身体",
    "病史",
    "高血压",
    "糖尿病",
    "忌口",
    "注意",
    "吃什么",
    "能不能吃",
    "情绪",
    "认知",
    "卧床",
    "护理",
    "家属",
)

# 急症的对话版固定回答：不复用记录草稿的五段式，那是给输入框用的
CHAT_REDLINE_REPLY = (
    "先按应急流程处理：立刻确认老人当前状态，必要时拨打 120，同时联系家属和站点。"
    "这类情况不要在线判断病情，现场以专业医护意见为准。"
)
CHAT_OUT_OF_SCOPE_REPLY = (
    "退款、改价、催款、改派和投诉升级我处理不了，请直接找站点管家。"
    "订单时间、地址、老人注意事项和记录怎么填，我可以帮你说明。"
)
CHAT_UNKNOWN_REPLY = "这个问题我从订单里找不到依据，建议联系站点管家确认。"

CHAT_GUARD_WARNING = "chat_guard"
CHAT_NUMBER_WARNING = "chat_number_guard"
CHAT_TRUNCATED_WARNING = "chat_truncated"
# 回答上限按 prompt 里的 120 字留出余量：模型偶尔超写，截断比整段丢弃友好
CHAT_MAX_CHARS = 400


def classify_chat_intent(question: str) -> str:
    """按关键词判断员工在问哪一类问题；未知问题归为 order（事实最全）。"""
    text = question or ""
    if any(word in text for word in _SCOPE_BLOCKERS):
        return CHAT_INTENT_OUT_OF_SCOPE
    if any(word in text for word in _FLOW_KEYWORDS):
        return CHAT_INTENT_FLOW
    if any(word in text for word in _ELDER_KEYWORDS):
        return CHAT_INTENT_ELDER
    return CHAT_INTENT_ORDER


def chat_short_circuit(question: str) -> tuple[str, str] | None:
    """急症与越界问题由代码直接答，不让模型参与，也不消耗额度。"""
    if hit_redline(question):
        return (REDLINE_WARNING, CHAT_REDLINE_REPLY)
    if classify_chat_intent(question) == CHAT_INTENT_OUT_OF_SCOPE:
        return ("out_of_scope", CHAT_OUT_OF_SCOPE_REPLY)
    return None


# 模型会把 prompt 里的标签名、字段名当成人话漏出去（实测输出了「facts 里没有家属电话」），
# 历史里的这类词也会被下一轮模仿，所以在入口与历史两侧都洗一下
_INTERNAL_TERM_RE = re.compile(r"</?facts>|</?history>", re.IGNORECASE)
# 「facts 里没有」要变成「订单信息里没有」，不能留一个空格变成「订单信息 里没有」
_FACTS_WORD_RE = re.compile(r"facts\s*里", re.IGNORECASE)


def clean_internal_terms(text: str) -> str:
    """把内部术语换成人话：员工不该看到 facts、prompt、标签这类词。"""
    return _INTERNAL_TERM_RE.sub("订单信息", _FACTS_WORD_RE.sub("订单信息里", text))


def trim_chat_history(
    history: list[dict[str, Any]], *, max_messages: int, max_chars: int
) -> list[dict[str, str]]:
    """裁剪历史：只留最近若干条，单条限长并脱敏。

    历史由前端随请求带上、不落库：老人档案复述进审计比省一次请求更危险。
    ``max_messages`` 是消息条数（一问一答算两条），不是轮数。
    """
    cleaned: list[dict[str, str]] = []
    for item in list(history or [])[-max_messages:]:
        role = "user" if str(item.get("role")) == "user" else "assistant"
        # 先脱敏再洗术语：上一轮漏出的「facts」会被本轮原样模仿
        content = clean_internal_terms(scrub(str(item.get("content") or "")))
        content = content[:max_chars].strip()
        if content:
            cleaned.append({"role": role, "content": content})
    return cleaned


def numbers_in_facts(text: str, facts_text: str) -> bool:
    """回答里的数字是否都能在事实里找到；对话场景只用它告警，不回滚内容。"""
    return _numbers_ok(text, facts_text)


# 流式切点必须避开的串：切开后两半都匹配不到正则，脱敏与拦截会同时失效
_SENSITIVE_PATTERNS = (
    _PHONE_RE,
    _ID_CARD_RE,
    _DOOR_RE,
    _MEDICAL_ADVICE_RE,
    _PROMISE_RE,
)
_SENTENCE_ENDS = ("。", "！", "？", "；", "\n")
_CLAUSE_ENDS = ("，", "、", ",", "；", ";", "。", "！", "？", "\n")


def _splits_sensitive(text: str, cut: int, *, window: int = 40) -> bool:
    """切点是否落在某个敏感匹配的内部；窗口按最长正则留足余量。"""
    start = max(0, cut - window)
    end = min(len(text), cut + window)
    for pattern in _SENSITIVE_PATTERNS:
        for match in pattern.finditer(text, start, end):
            if match.start() < cut < match.end():
                return True
    return False


def _drop_spans(text: str) -> str:
    """删掉越界措辞直到下个分句结束，供无句读的长片段使用。

    只删「建议停用」会留下「降压药」这种半截医嘱，干脆整小句拿掉。
    """
    while True:
        match = None
        for pattern in (_MEDICAL_ADVICE_RE, _PROMISE_RE):
            found = pattern.search(text)
            if found and (match is None or found.start() < match.start()):
                match = found
        if match is None:
            return text
        tail = text[match.end() :]
        offset = next(
            (index for index, char in enumerate(tail) if char in _CLAUSE_ENDS),
            len(tail),
        )
        text = text[: match.start()] + tail[offset:]


def guard_chat_text(
    text: str, *, facts_text: str, max_chars: int = CHAT_MAX_CHARS
) -> tuple[str, list[str]]:
    """整段回答的收尾校验（JSON 接口用）。

    与记录草稿的区别：这里删掉越界句但不整段判死。对话里「答不上来」
    比「答得略保守」更伤信任，而且流式已发出的字本来也收不回来。
    """
    warnings: list[str] = []
    kept: list[str] = []
    for sentence in _split_sentences(scrub(text)):
        if _MEDICAL_ADVICE_RE.search(sentence) or _PROMISE_RE.search(sentence):
            warnings.append(CHAT_GUARD_WARNING)
            continue
        kept.append(sentence)
    answer = clean_internal_terms("".join(kept)).strip()
    if len(answer) > max_chars:
        answer = answer[:max_chars].rstrip()
        warnings.append(CHAT_TRUNCATED_WARNING)
    if answer and not _numbers_ok(answer, facts_text):
        # 编造时间/金额/年龄的风险要让人看见，但不在对话里把整句删成空白
        warnings.append(CHAT_NUMBER_WARNING)
    return answer, list(dict.fromkeys(warnings))


class ChatStreamGuard:
    """流式回答的增量过滤：整句判定，跨 chunk 的半句先攒着。

    三条约束：
    1. 只在句读处放出；没句读时最多憋 ``HOLD_CHARS`` 字就放一段，否则前端一直空白；
    2. 切点不得落在手机号/身份证/门牌/越界措辞内部：一劈开，两半都匹配不到正则；
    3. 医疗建议句、承诺句：有句读的整句丢弃，无句读的只删措辞，不静默改写。
    """

    HOLD_CHARS = 60

    def __init__(self, *, facts_text: str, max_chars: int = CHAT_MAX_CHARS) -> None:
        self._facts_text = facts_text
        self._max_chars = max_chars
        self._buffer = ""
        self._emitted = 0
        self.warnings: list[str] = []

    def feed(self, chunk: str) -> str:
        """吃进一段模型增量，返回可立即下发的文本（可能为空）。"""
        if not chunk or self._emitted >= self._max_chars:
            return ""
        self._buffer += chunk
        pieces: list[str] = []
        while True:
            sentences = _split_sentences(self._buffer)
            if len(sentences) < 2:
                break
            pieces.append("".join(sentences[:-1]))
            self._buffer = sentences[-1]
        while len(self._buffer) > self.HOLD_CHARS:
            cut = self._safe_cut(self._buffer)
            if cut <= 0:
                # 整个窗口都落在敏感串里（极端情况），等下一个 chunk 再说
                break
            pieces.append(self._buffer[:cut])
            self._buffer = self._buffer[cut:]
        return self._render(pieces)

    def flush(self) -> str:
        """把残留的半句放出去；模型停在这里就说明它已经说完了。"""
        text = self._render([self._buffer] if self._buffer else [])
        self._buffer = ""
        return text

    @classmethod
    def _safe_cut(cls, text: str) -> int:
        """找一个不会把敏感串或越界措辞劈开的切点；找不到返回 0（继续等）。

        只避开数字是不够的：门牌「3号楼」、措辞「建议停用」被劈开后，
        两半都匹配不到正则，连带脱敏与医疗拦截一起失效。
        """
        cut = min(cls.HOLD_CHARS, len(text))
        while 0 < cut < len(text):
            if (
                text[cut - 1].isdigit()
                or text[cut].isdigit()
                or _splits_sensitive(text, cut)
            ):
                cut -= 1
                continue
            break
        return max(0, cut)

    def _render(self, pieces: list[str]) -> str:
        out: list[str] = []
        for piece in pieces:
            for sentence in _split_sentences(piece):
                if _MEDICAL_ADVICE_RE.search(sentence) or _PROMISE_RE.search(sentence):
                    if sentence.endswith(_SENTENCE_ENDS):
                        # 完整句子直接丢：留着半句会让人以为话说完了
                        self._warn(CHAT_GUARD_WARNING)
                        continue
                    # 无句读的长片段：只删越界措辞，整段丢弃会在回答中间凭空少一截
                    sentence = _drop_spans(sentence)
                    self._warn(CHAT_GUARD_WARNING)
                cleaned = clean_internal_terms(scrub(sentence))
                if cleaned:
                    out.append(cleaned)
        text = "".join(out)
        remaining = self._max_chars - self._emitted
        if len(text) > remaining:
            text = text[:remaining]
            self._warn(CHAT_TRUNCATED_WARNING)
        self._emitted += len(text)
        return text

    def _warn(self, code: str) -> None:
        if code not in self.warnings:
            self.warnings.append(code)

    def finalize(self, answer: str) -> list[str]:
        """收尾：数字对不上只记告警，前端据此提示「以订单为准」。"""
        if answer and not _numbers_ok(answer, self._facts_text):
            self._warn(CHAT_NUMBER_WARNING)
        return list(self.warnings)
