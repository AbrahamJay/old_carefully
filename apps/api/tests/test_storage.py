"""存储端口的契约测试：不依赖网络，也不碰真实 MinIO。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.core.errors import NotFoundError
from app.infra.ports import StoredObject
from app.infra.storage import LocalFileStorage, MinioFileStorage
from app.modules.files.service import FileService


class FakeStorage:
    """满足 FileStorage 协议的内存实现。"""

    def __init__(self, name: str, *, public: bool = True) -> None:
        self.name = name
        self._public = public
        self.objects: dict[str, bytes] = {}

    def save(self, content: bytes, *, key: str, content_type: str) -> None:
        self.objects[key] = content

    def open(self, key: str) -> StoredObject:
        if key not in self.objects:
            raise NotFoundError("文件不存在")
        payload = self.objects[key]
        return StoredObject(stream=iter([payload]), length=len(payload))

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def public_url(self, key: str) -> str | None:
        return f"https://{self.name}.example.com/{key}" if self._public else None


def test_local_storage_roundtrip(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path)

    storage.save(b"hello", key="a.png", content_type="image/png")
    stored = storage.open("a.png")

    assert b"".join(stored.stream) == b"hello"
    assert stored.length == 5
    assert storage.public_url("a.png") is None

    storage.delete("a.png")
    with pytest.raises(NotFoundError):
        storage.open("a.png")


def test_local_storage_blocks_path_traversal(tmp_path) -> None:
    (tmp_path / "secret.txt").write_text("secret")
    storage = LocalFileStorage(tmp_path / "root")

    with pytest.raises(NotFoundError):
        storage.open("../secret.txt")
    with pytest.raises(NotFoundError):
        storage.save(b"x", key="../evil.png", content_type="image/png")


def test_minio_public_url_uses_configured_base(monkeypatch) -> None:
    monkeypatch.setattr(settings, "minio_public_base_url", "http://cdn.example.com/media")
    storage = MinioFileStorage(
        endpoint="localhost:9000", access_key="k", secret_key="s", bucket="media"
    )

    assert storage.public_url("a.png") == "http://cdn.example.com/media/a.png"
    assert storage.name == "minio"


def test_direct_url_routes_by_record_storage(monkeypatch) -> None:
    monkeypatch.setattr(settings, "file_delivery", "redirect")
    current, fallback = FakeStorage("minio"), FakeStorage("local")
    service = FileService(None, current, fallback=fallback)  # type: ignore[arg-type]

    # 写入介质按记录决定：新文件走 MinIO，历史文件回落到本地
    assert service.direct_url("a.png", SimpleNamespace(storage="minio")) == (
        "https://minio.example.com/a.png"
    )
    assert service.direct_url("a.png", SimpleNamespace(storage="local")) == (
        "https://local.example.com/a.png"
    )


def test_direct_url_disabled_in_proxy_mode(monkeypatch) -> None:
    monkeypatch.setattr(settings, "file_delivery", "proxy")
    service = FileService(None, FakeStorage("minio"))  # type: ignore[arg-type]

    assert service.direct_url("a.png", SimpleNamespace(storage="minio")) is None


def test_open_stream_falls_back_for_unrecorded_file() -> None:
    current, fallback = FakeStorage("minio"), FakeStorage("local")
    fallback.objects["legacy.png"] = b"legacy"
    service = FileService(None, current, fallback=fallback)  # type: ignore[arg-type]

    # 切换存储前的存量文件没有归属记录，应从旧介质读回
    assert b"".join(service.open_stream("legacy.png", None).stream) == b"legacy"
    with pytest.raises(NotFoundError):
        service.open_stream("missing.png", None)
