"""外部适配器的契约（端口）。

用 ``Protocol`` 而非抽象基类：实现方无需显式继承，测试替身可以直接鸭子类型传入。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ChargeResult:
    provider: str
    transaction_id: str
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class OnlinePaymentGateway(Protocol):
    name: str

    def charge(self, amount_cents: int, *, kind: str, operator_id: int | None) -> ChargeResult:
        """发起在线收款，返回交易流水信息（不负责落库）。"""
        ...


@dataclass
class StoredObject:
    """一次读请求的结果：字节流 + 元信息。

    ``stream`` 是同步迭代器，交给 ``StreamingResponse`` 消费；
    消费方必须保证最终调用 ``close()`` 释放底层连接（对象存储的连接池很紧）。
    """

    stream: Iterator[bytes]
    length: int = 0
    content_type: str = ""
    close: Callable[[], None] = field(default=lambda: None)


@runtime_checkable
class FileStorage(Protocol):
    """对象存储端口。

    只描述「字节在哪」这类存储语义，不暴露 ``Path``：
    MinIO/S3 类实现没有本地路径，硬套 Path 只会逼出临时文件。
    ``key`` 由调用方生成（不可猜），实现方只负责落地与取回。
    """

    name: str

    def save(self, content: bytes, *, key: str, content_type: str) -> None:
        """写入对象；同 key 覆盖。"""
        ...

    def open(self, key: str) -> StoredObject:
        """读取对象；key 不存在时抛 ``NotFoundError``。"""
        ...

    def delete(self, key: str) -> None:
        """删除对象；不存在时静默成功。"""
        ...

    def public_url(self, key: str) -> str | None:
        """匿名可读的直链；不支持直链的实现（本地磁盘）返回 None。"""
        ...
