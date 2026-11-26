"""Agent 模块：LLM 辅助能力（记录代写、服务前提示）。

统一底座（阶段五起生效，阶段七复用）：
- ``models.py``：自写 ``BaseChatModel`` 适配 OpenAI 兼容网关，httpx 只出现在这里；
- ``runtime.py``：LangGraph 图编排的唯一入口，单轮场景也是图；
- ``tools.py``：只读事实层，阶段七绑定给模型时复用同一份定义；
- ``policies.py``：脱敏、急症红线、结构校验与医疗措辞后置检查；
- ``audit.py``：每次模型调用写入 ``agent_actions``，失败也留痕；
- ``service.py`` / ``router.py``：开关、配额与 ``/agent/*`` 端点。

图只产出文本，任何写操作仍走原有业务接口，AI 不可用时主流程不受影响。
"""

from __future__ import annotations

import warnings

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

# 第三方 langgraph 在导入期会抛一条与业务无关的 pending deprecation 警告，
# 每次启动/跑测试都会刷屏，这里只屏蔽这一条，不影响其它告警。
# 必须在导入 langchain_core 之后再注册：它会在自己导入时把该类别恢复为 default。
warnings.filterwarnings(
    "ignore",
    message=r"The default value of `allowed_objects` will change.*",
    category=LangChainPendingDeprecationWarning,
)

from .service import AgentService

__all__ = ["AgentService"]
