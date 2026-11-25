"""对象存储适配器：本地磁盘与 MinIO（S3 兼容）。

两个实现都满足 ``FileStorage`` 端口，业务层无需感知介质差异；
``build_storage`` 按配置装配，切换存储只改环境变量。
"""

from __future__ import annotations

import json
import logging
import mimetypes
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

from minio import Minio
from minio.error import S3Error

from ..core.config import settings
from ..core.enums import StorageProvider
from ..core.errors import ExternalServiceError, NotFoundError
from .ports import FileStorage, StoredObject

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 64 * 1024
_NOT_FOUND_CODES = frozenset({"NoSuchKey", "NoSuchObject", "NoSuchBucket"})


def public_read_only_policy(bucket: str) -> dict[str, Any]:
    """匿名只读策略：允许按 key 读取，但不允许列举对象。

    图片靠 ``<img src>`` 直连展示，需要匿名 GetObject；
    不授予 ListBucket，避免整桶对象清单被遍历。
    """
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/*"],
            }
        ],
    }


class LocalFileStorage:
    """本地磁盘实现，用于开发与小规模部署。"""

    name = StorageProvider.LOCAL

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def save(self, content: bytes, *, key: str, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def open(self, key: str) -> StoredObject:
        path = self._path(key)
        if not path.is_file():
            raise NotFoundError("文件不存在")
        handle = path.open("rb")

        def _iter() -> Iterator[bytes]:
            with handle:
                while chunk := handle.read(_CHUNK_SIZE):
                    yield chunk

        return StoredObject(
            stream=_iter(),
            length=path.stat().st_size,
            # 磁盘上没有元数据，按扩展名推断，避免存量图退化成 octet-stream
            content_type=mimetypes.guess_type(path.name)[0] or "",
            close=handle.close,
        )

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def public_url(self, key: str) -> str | None:
        return None

    def _path(self, key: str) -> Path:
        candidate = (self._root / key).resolve()
        # 关键：key 来自 URL，必须阻断 ../ 与绝对路径穿越
        if self._root not in candidate.parents:
            raise NotFoundError("文件不存在")
        return candidate


class MinioFileStorage:
    """MinIO / S3 兼容对象存储实现。

    桶采用懒初始化：启动期不探测，避免对象存储抖动导致 API 起不来。
    """

    name = StorageProvider.MINIO

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        region: str = "",
    ) -> None:
        self._bucket = bucket
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region or None,
        )
        self._bucket_ready = False

    @property
    def client(self) -> Minio:
        """暴露底层 client，供运维脚本建桶/设策略复用。"""
        return self._client

    def save(self, content: bytes, *, key: str, content_type: str) -> None:
        self._ensure_bucket()
        try:
            self._client.put_object(
                self._bucket,
                key,
                BytesIO(content),
                len(content),
                content_type=content_type or "application/octet-stream",
            )
        except S3Error as exc:
            logger.exception("minio put_object failed: bucket=%s key=%s", self._bucket, key)
            raise ExternalServiceError("图片保存失败，请稍后重试") from exc

    def open(self, key: str) -> StoredObject:
        try:
            response = self._client.get_object(self._bucket, key)
        except S3Error as exc:
            if exc.code in _NOT_FOUND_CODES:
                raise NotFoundError("文件不存在") from exc
            logger.exception("minio get_object failed: bucket=%s key=%s", self._bucket, key)
            raise ExternalServiceError("图片读取失败，请稍后重试") from exc

        released = False

        def _release() -> None:
            # urllib3 连接池很紧，漏释放会在压测时表现为「请求全部挂住」
            nonlocal released
            if released:
                return
            released = True
            try:
                response.close()
                response.release_conn()
            except Exception:  # 释放失败不应影响已经开始的响应
                logger.warning("minio response release failed", exc_info=True)

        def _iter() -> Iterator[bytes]:
            try:
                yield from response.stream(_CHUNK_SIZE)
            finally:
                _release()

        return StoredObject(
            stream=_iter(),
            length=int(response.headers.get("Content-Length") or 0),
            content_type=response.headers.get("Content-Type") or "",
            close=_release,
        )

    def delete(self, key: str) -> None:
        try:
            self._client.remove_object(self._bucket, key)
        except S3Error as exc:
            logger.warning("minio remove_object failed: key=%s err=%s", key, exc)

    def public_url(self, key: str) -> str | None:
        return f"{settings.minio_public_base}/{key}"

    def ensure_bucket(self, *, public_read: bool = True) -> None:
        """幂等建桶；``public_read`` 时同时设置匿名只读策略。"""
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
            logger.info("minio bucket created: %s", self._bucket)
        if public_read:
            self._client.set_bucket_policy(
                self._bucket, json.dumps(public_read_only_policy(self._bucket))
            )
        self._bucket_ready = True

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            self.ensure_bucket()
        except S3Error as exc:
            logger.exception("minio bucket init failed: %s", self._bucket)
            raise ExternalServiceError("图片存储未就绪，请联系管理员") from exc


def build_storage() -> FileStorage:
    """按 ``STORAGE_PROVIDER`` 装配当前存储。"""
    if settings.storage_provider == StorageProvider.MINIO:
        return MinioFileStorage(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
            secure=settings.minio_secure,
            region=settings.minio_region,
        )
    return LocalFileStorage(settings.upload_dir)


def build_local_storage() -> FileStorage:
    """本地兜底：切换存储后用于继续读取历史文件。"""
    return LocalFileStorage(settings.upload_dir)


__all__ = [
    "LocalFileStorage",
    "MinioFileStorage",
    "build_local_storage",
    "build_storage",
    "public_read_only_policy",
]
