"""模型适配器：把 OpenAI 兼容网关翻译成 LangChain 的 ``BaseChatModel``。

设计边界（与阶段七共用同一份实现，不再另起一套调用方式）：
- 只做「协议翻译 + 故障翻译」，不拼 prompt、不做业务校验、不写数据库；
- httpx 只出现在本文件，业务代码永远只见 ``model.invoke(messages)``；
- 上游异常一律翻译成 ``AgentUnavailableError`` / ``AgentContentBlockedError``，
  编排层只认领域错误，不需要理解 HTTP 状态码。

适配点是真实的：DeepSeek 等网关会返回 ``reasoning_content``、对 ``max_tokens``
的命名不一致、JSON 模式只支持 ``json_object``，这些都收敛在这里。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import httpx
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field, SecretStr

from ...core.config import settings
from .errors import AgentContentBlockedError, AgentRateLimitedError, AgentUnavailableError

logger = logging.getLogger(__name__)

# 连接复用：模型调用是高频短请求，复用连接池能省掉大部分 TLS 握手开销。
_CLIENT = httpx.Client(
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    follow_redirects=False,
)


@dataclass(frozen=True)
class AgentCapabilities:
    """网关能力声明：由配置决定，不做运行时探测，避免每次启动都打一次外部请求。"""

    json_mode: bool = True
    streaming: bool = True
    tools: bool = False


def _to_openai_message(message: BaseMessage) -> dict[str, Any]:
    """把 LangChain 消息压成 OpenAI 结构；多段内容只保留文本（本系统不发图）。"""
    if isinstance(message, SystemMessage):
        role = "system"
    elif isinstance(message, HumanMessage):
        role = "user"
    elif isinstance(message, AIMessage):
        role = "assistant"
    elif isinstance(message, ToolMessage):
        role = "tool"
    else:
        role = "user"

    content = message.content
    if isinstance(content, list):
        # 个别模板会产出 [{"type": "text", "text": ...}]，统一拼成纯文本
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return {"role": role, "content": content or ""}


class CommunityChatModel(BaseChatModel):
    """OpenAI 兼容网关适配器。

    ``model_name`` 与网关的 ``model`` 字段对应；密钥用 ``SecretStr`` 防止被日志或
    traceback 带出来。超时、输出上限都在构造时注入，单次调用可通过 ``kwargs`` 覆盖
    （阶段七的轻模型需要一个更短的上限）。
    """

    model_name: str
    base_url: str
    api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    timeout_seconds: float = 30.0
    default_max_tokens: int = 800
    # 部分网关只认 max_completion_tokens，用配置切换而不是改代码
    max_tokens_param: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    json_mode: bool = True
    supports_streaming: bool = True
    # 混合思考模型（DeepSeek V4 等）默认先输出推理：既计费又占满 max_tokens，
    # 长用例会被截断成非 JSON。支持 thinking.type=disabled 的网关可显式关掉。
    disable_thinking: bool = True

    @property
    def _llm_type(self) -> str:
        return "community-chat"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_name": self.model_name, "base_url": self.base_url}

    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            json_mode=self.json_mode,
            streaming=self.supports_streaming,
            # M5 不开放模型自主选工具；阶段七由上层图绑定工具后再打开
            tools=False,
        )

    # ------------------------------------------------------------ HTTP 细节
    def _endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

    def _payload(
        self,
        messages: list[BaseMessage],
        *,
        stop: list[str] | None,
        stream: bool,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": kwargs.get("model_name", self.model_name),
            "messages": [_to_openai_message(message) for message in messages],
            "temperature": kwargs.get("temperature", 0.2),
            self.max_tokens_param: kwargs.get("max_tokens", self.default_max_tokens),
        }
        if stop:
            payload["stop"] = stop
        if kwargs.get("json_mode", self.json_mode):
            # DeepSeek 等网关只支持 json_object（不支持 json_schema），schema 校验由场景层做
            payload["response_format"] = {"type": "json_object"}
        if self.disable_thinking:
            # 不支持该字段的网关请把 LLM_DISABLE_THINKING 设为 false，否则会 400
            payload["thinking"] = {"type": "disabled"}
        if stream:
            payload["stream"] = True
            # 不加这一项，流式响应拿不到 usage，成本统计会整体失真
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _raise_for_status(self, response: httpx.Response, body: str) -> None:
        """把网关错误翻译成领域异常；日志里只留状态码与截断后的 body 摘要。"""
        status = response.status_code
        if status == 429:
            raise AgentRateLimitedError("AI 服务繁忙，请稍后再试")
        if status in (401, 403):
            logger.warning("Agent 网关鉴权失败：status=%s body=%.200s", status, body)
            raise AgentUnavailableError("AI 服务鉴权失败，请联系管理员检查配置")
        if status >= 500:
            logger.warning("Agent 网关 5xx：status=%s body=%.200s", status, body)
            raise AgentUnavailableError()
        logger.warning("Agent 网关返回异常：status=%s body=%.200s", status, body)
        raise AgentUnavailableError("AI 服务返回异常，请稍后再试")

    def _parse_error_body(self, data: dict[str, Any]) -> None:
        """部分国内网关会用 200 返回 ``error`` 字段，需要再判一次。"""
        error = data.get("error")
        if not error:
            return
        text = json.dumps(error, ensure_ascii=False)[:200]
        logger.warning("Agent 网关业务错误：%s", text)
        if "rate" in text.lower() or "quota" in text.lower():
            raise AgentRateLimitedError("AI 服务繁忙，请稍后再试")
        if "content" in text.lower() and ("filter" in text.lower() or "policy" in text.lower()):
            raise AgentContentBlockedError()
        raise AgentUnavailableError()

    @staticmethod
    def _extract_usage(data: dict[str, Any]) -> tuple[int, int]:
        usage = data.get("usage") or {}
        return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)

    # ------------------------------------------------------------ 非流式
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload = self._payload(messages, stop=stop, stream=False, **kwargs)
        started = time.perf_counter()
        try:
            response = _CLIENT.post(
                self._endpoint(),
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise AgentUnavailableError("AI 服务响应超时") from exc
        except httpx.HTTPError as exc:
            logger.warning("Agent 网关连接失败：%s", exc)
            raise AgentUnavailableError("AI 服务连接失败") from exc

        if response.status_code != 200:
            self._raise_for_status(response, response.text)

        try:
            data = response.json()
        except ValueError as exc:
            raise AgentUnavailableError("AI 服务返回了无法解析的内容") from exc
        self._parse_error_body(data)

        choices = data.get("choices") or []
        if not choices:
            raise AgentUnavailableError("AI 返回内容为空")
        choice = choices[0]
        message = choice.get("message") or {}
        # 推理模型会把答案放在 reasoning_content；content 为空时用它兜底，避免空草稿
        content = message.get("content") or message.get("reasoning_content") or ""
        if choice.get("finish_reason") == "content_filter":
            raise AgentContentBlockedError()

        tokens_in, tokens_out = self._extract_usage(data)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))],
            llm_output={
                "model": data.get("model", self.model_name),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
                "finish_reason": choice.get("finish_reason", ""),
            },
        )

    # ------------------------------------------------------------ 流式
    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """同步 SSE 解析：阶段七的抽屉做打字机效果时直接复用，无需换模型类。"""
        if not self.supports_streaming:
            result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            yield ChatGenerationChunk(message=AIMessageChunk(content=result.generations[0].text))
            return

        payload = self._payload(messages, stop=stop, stream=True, **kwargs)
        try:
            with _CLIENT.stream(
                "POST",
                self._endpoint(),
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            ) as response:
                if response.status_code != 200:
                    self._raise_for_status(response, response.read().decode("utf-8", "ignore"))
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[len("data:") :].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk)
                    except ValueError:
                        continue
                    self._parse_error_body(data)
                    choices = data.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}).get("content")
                    if not delta:
                        continue
                    if run_manager is not None:
                        run_manager.on_llm_new_token(delta)
                    yield ChatGenerationChunk(message=AIMessageChunk(content=delta))
        except httpx.TimeoutException as exc:
            raise AgentUnavailableError("AI 服务响应超时") from exc
        except httpx.HTTPError as exc:
            raise AgentUnavailableError("AI 服务连接失败") from exc


# 固定回复同时覆盖两个场景的字段：测试只关心「能解析出结构」，不关心具体措辞。
MOCK_REPLY = json.dumps(
    {
        "content": (
            "服务内容：陪同老人前往医院复查，协助挂号、候诊并取药。\n"
            "老人状态：精神状态良好，医生反馈血压控制平稳。\n"
            "异常与风险：无。\n"
            "下次安排：下周三复诊。\n"
            "照片：2 张。"
        ),
        "prep_brief": ["高血压，提醒按时服药", "糖尿病，留意低血糖表现", "复诊后拍照反馈家属"],
        "items": ["高血压，提醒按时服药", "糖尿病，留意低血糖表现"],
        # 管理端解释场景：mock 不给 staff_id，护栏会默认取规则第一名
        "summary": "技能与站点均匹配，当前负载尚有余量",
        "why": ["同属本单服务区域", "技能匹配本单服务项目"],
        "risks": ["今日已有派单，需留意前序订单进度"],
        "data_gaps": [],
        "what_happened": "订单已派出但超过阈值仍未接单。",
        "next_actions": [
            {"action": "call_staff", "label": "电话联系服务人员"},
            {"action": "reassign", "label": "改派给其他员工"},
        ],
        "escalate": False,
    },
    ensure_ascii=False,
)


class MockChatModel(BaseChatModel):
    """离线替身：无密钥也能跑通全链路，同时用于测试与评测集回归。"""

    model_name: str = "mock"
    reply: str = ""

    @property
    def _llm_type(self) -> str:
        return "mock"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = self.reply or MOCK_REPLY
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))],
            llm_output={
                "model": "mock",
                "tokens_in": 0,
                "tokens_out": 0,
                "latency_ms": 0,
                "finish_reason": "stop",
            },
        )


@lru_cache
def build_chat_model() -> BaseChatModel:
    """按配置构造模型单例；配置错误时提前抛错，不在请求路径上才发现。"""
    if settings.llm_provider == "mock" or not settings.llm_base_url:
        return MockChatModel()
    return CommunityChatModel(
        model_name=settings.llm_model,
        base_url=settings.llm_base_url,
        api_key=SecretStr(settings.llm_api_key),
        timeout_seconds=settings.llm_timeout_seconds,
        default_max_tokens=settings.llm_max_tokens,
        disable_thinking=settings.llm_disable_thinking,
    )
