"""Agent 专属异常。

统一继承 ``AppError``，路由层无需额外包装：错误处理器会按 ``http_status`` 返回，
前端只需判断 503（可降级手写）与 429（额度用尽）两种主要情况。
"""

from __future__ import annotations

from ...core.errors import AppError, FeatureUnavailableError


class AgentUnavailableError(FeatureUnavailableError):
    """模型网关不可用、超时或未配置：业务主流程必须能继续，前端回退到手工填写。"""

    code = "agent_unavailable"
    http_status = 503
    default_message = "AI 服务暂时不可用，请稍后再试或手工填写"


class AgentRateLimitedError(AppError):
    """单人单日额度用尽：与网关的 429 区分开，前者是我们自己的成本护栏。"""

    code = "agent_rate_limited"
    http_status = 429
    default_message = "今日 AI 使用次数已达上限，请明天再试"


class AgentContentBlockedError(AppError):
    """模型侧安全拦截：需要提示用户调整措辞，而不是笼统报服务不可用。"""

    code = "agent_content_blocked"
    http_status = 422
    default_message = "内容未通过安全校验，请调整后再试"
