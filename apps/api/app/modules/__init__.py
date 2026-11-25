"""业务模块。

每个子包内部按 "router / service / repository / schemas" 纵向分层，
对外只暴露 ``__init__`` 中声明的门面，跨模块调用一律通过门面。
"""
