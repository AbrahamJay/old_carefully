"""密码哈希校验的单元测试：不碰数据库，但走 conftest 的测试库准备流程。"""

from __future__ import annotations

from app.core.security import hash_password, verify_password


def test_verify_password_accepts_matching_hash() -> None:
    hashed = hash_password("Admin123!")
    assert verify_password("Admin123!", hashed) is True
    assert verify_password("Admin123", hashed) is False


def test_verify_password_rejects_non_argon2_value() -> None:
    """库里被手工写入明文（或截断的哈希）时只能返回 False，不能让接口抛 500。"""
    assert verify_password("Admin123!", "Admin123!") is False
    assert verify_password("Admin123!", "$argon2id$broken") is False
    assert verify_password("Admin123!", None) is False
