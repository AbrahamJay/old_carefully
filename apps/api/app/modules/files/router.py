from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from starlette.background import BackgroundTask

from ...api.deps import get_current_user, get_file_service, get_file_viewer
from ...db.models import User
from .schemas import UploadOut
from .service import FileService

router = APIRouter(tags=["文件"])

# key 是不可变的 uuid，图片内容不会变，可放心长缓存
_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"


@router.post("/uploads", response_model=UploadOut)
async def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    service: FileService = Depends(get_file_service),
) -> UploadOut:
    content = await file.read()
    record = service.save_image(user, content_type=file.content_type or "", content=content)
    return UploadOut(key=record.key, url=service.url_of(record.key))


@router.get(
    "/files/{key}",
    response_model=None,
    responses={
        200: {"content": {"image/*": {}}, "description": "图片字节流"},
        302: {"description": "重定向到对象存储直链"},
    },
)
def get_file(
    key: str,
    viewer: User | None = Depends(get_file_viewer),
    service: FileService = Depends(get_file_service),
) -> StreamingResponse | RedirectResponse:
    record = service.authorize(key, viewer)

    # 对象存储直链：302 让浏览器直接去 MinIO 取图，不占 API 带宽
    direct = service.direct_url(key, record)
    if direct is not None:
        return RedirectResponse(
            direct, status_code=302, headers={"Cache-Control": _IMMUTABLE_CACHE}
        )

    stored = service.open_stream(key, record)
    headers = {"Cache-Control": _IMMUTABLE_CACHE}
    if stored.length:
        headers["Content-Length"] = str(stored.length)
    return StreamingResponse(
        stored.stream,
        media_type=stored.content_type or "application/octet-stream",
        headers=headers,
        # 必须显式释放：MinIO 底层是 urllib3 连接池
        background=BackgroundTask(stored.close),
    )
