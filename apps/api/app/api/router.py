"""路由聚合。

每个模块自带完整路径，聚合层只负责拼装顺序，不承载任何业务逻辑。
"""

from __future__ import annotations

from fastapi import APIRouter

from ..modules.admin.router import router as admin_router
from ..modules.agents.router import router as agents_router
from ..modules.auth.router import router as auth_router
from ..modules.catalog.router import router as catalog_router
from ..modules.elders.router import router as elders_router
from ..modules.files.router import router as files_router
from ..modules.notifications.router import router as notifications_router
from ..modules.orders.router import router as orders_router
from ..modules.org.router import router as org_router
from ..modules.tasks.router import router as tasks_router

api_router = APIRouter(prefix="/api/v1")

for module_router in (
    auth_router,
    elders_router,
    catalog_router,
    orders_router,
    files_router,
    notifications_router,
    org_router,
    admin_router,
    tasks_router,
    agents_router,
):
    api_router.include_router(module_router)

__all__ = ["api_router"]
