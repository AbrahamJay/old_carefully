from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.config import settings
from ...core.enums import Role
from ...core.errors import BadRequestError, ForbiddenError, NotFoundError
from ...db.models import Order, UploadedFile, User
from ...domain.authz import can_access_order
from ...infra.ports import FileStorage, StoredObject

ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class FileService:
    """图片上传与读取。

    ``storage`` 是当前写入介质，``fallback`` 用于继续读取切换存储前
    落在旧介质（如本地磁盘）上的历史文件，因此换存储不需要停机迁移。
    归属关系落在 ``uploaded_files`` 表，为下载鉴权与后续清理提供依据。
    """

    def __init__(
        self,
        db: Session,
        storage: FileStorage,
        fallback: FileStorage | None = None,
    ) -> None:
        self._db = db
        self._storage = storage
        self._fallback = fallback

    def save_image(self, actor: User, *, content_type: str, content: bytes) -> UploadedFile:
        suffix = ALLOWED_IMAGE_TYPES.get(content_type)
        if suffix is None:
            raise BadRequestError("只支持 jpg/png/webp 图片")
        if not content:
            raise BadRequestError("文件为空")
        if len(content) > settings.upload_max_bytes:
            raise BadRequestError(f"图片不能超过 {settings.upload_max_bytes // (1024 * 1024)}MB")

        # key 由业务层生成：不可预测，且与存储介质无关
        key = f"{uuid.uuid4().hex}{suffix}"
        self._storage.save(content, key=key, content_type=content_type)
        record = UploadedFile(
            key=key,
            owner_id=actor.id,
            content_type=content_type,
            size_bytes=len(content),
            storage=str(self._storage.name),
        )
        self._db.add(record)
        self._db.commit()
        self._db.refresh(record)
        return record

    def url_of(self, key: str) -> str:
        return f"/api/v1/files/{key}"

    def authorize(self, key: str, viewer: User | None) -> UploadedFile | None:
        """校验读取权限；``viewer`` 为 None 表示当前未开启下载鉴权。"""
        record = self._record_of(key)
        if viewer is not None:
            self._assert_readable(record, viewer)
        return record

    def direct_url(self, key: str, record: UploadedFile | None) -> str | None:
        """公开桶 + redirect 模式下返回对象存储直链，图片流量不经过 API。"""
        # 无归属记录的文件不猜介质，交给 open_stream 给出准确的 404
        if record is None or settings.file_delivery != "redirect":
            return None
        return self._storage_of(record).public_url(key)

    def open_stream(self, key: str, record: UploadedFile | None) -> StoredObject:
        if record is None:
            # 切换存储前的存量文件可能没有归属记录：依次尝试，取第一个命中的介质
            stored = self._open_first_hit(key)
        else:
            stored = self._storage_of(record).open(key)
        if not stored.content_type and record is not None:
            stored.content_type = record.content_type
        return stored

    # ------------------------------------------------------------------ 内部
    def _record_of(self, key: str) -> UploadedFile | None:
        return self._db.scalars(
            select(UploadedFile).where(UploadedFile.key == Path(key).name)
        ).first()

    def _storage_of(self, record: UploadedFile | None) -> FileStorage:
        """按记录落地的介质选择适配器，实现新旧存储并存读取。"""
        name = record.storage if record is not None and record.storage else None
        if name is None or name == self._storage.name:
            return self._storage
        if self._fallback is not None and name == self._fallback.name:
            return self._fallback
        raise NotFoundError("文件所在存储未配置，暂不可读")

    def _open_first_hit(self, key: str) -> StoredObject:
        """无记录时逐个介质试读；只有「对象不存在」才降级，其他故障照常上报。"""
        for storage in self._candidates():
            try:
                return storage.open(key)
            except NotFoundError:
                continue
        raise NotFoundError("文件不存在")

    def _candidates(self) -> list[FileStorage]:
        if self._fallback is None or self._fallback.name == self._storage.name:
            return [self._storage]
        return [self._storage, self._fallback]

    def _assert_readable(self, record: UploadedFile | None, viewer: User) -> None:
        if viewer.role == Role.ADMIN:
            return
        # 历史文件没有归属记录，鉴权开启后只允许管理员读取
        if record is None:
            raise ForbiddenError()
        if record.owner_id == viewer.id:
            return
        if record.order_id is not None:
            order = self._db.get(Order, record.order_id)
            if order is not None and can_access_order(self._db, viewer, order):
                return
        raise ForbiddenError()
