"""Agent 接入占位目录（后续需求，当前不实现）。

规划中的结构：
- ``tools.py``：把 service 层能力包装成 LLM 可调用的工具，
  与 HTTP 路由共用同一套业务规则，不重复实现。
- ``runtime.py``：会话状态、上下文拼装与 LLM 调用。
- ``router.py``：``/agent/*`` 接口，由 ``settings.agent_enabled`` 控制上下线。

保持空实现是刻意为之：Agent 依赖的 service 层已经就位，
后续只需在此目录新增文件，无需改动业务模块。
"""
