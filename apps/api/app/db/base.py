"""声明式基类。

单独放置是为了切断 ``models -> db`` 与 ``db -> models`` 的隐性循环依赖。
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
