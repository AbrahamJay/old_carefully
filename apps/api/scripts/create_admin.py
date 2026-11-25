"""创建或重置管理员账号。

生产/预发环境关闭了 ``AUTO_SEED``，首次部署用它开通后台入口。

用法：
    .venv/bin/python scripts/create_admin.py                          # 交互式输入
    .venv/bin/python scripts/create_admin.py --phone 13900000000 --name 张管家
    .venv/bin/python scripts/create_admin.py --phone 13900000000 --reset

密码默认交互输入（不回显、不写进 shell 历史）；``--password`` 仅用于自动化。
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# sys.path 先注入项目根，下面的 import 才能生效
from sqlalchemy import select

from app.core.enums import Role, UserStatus
from app.core.security import hash_password
from app.db import SessionLocal
from app.db.migrate import run_migrations
from app.db.models import Station, User

MIN_PASSWORD_LENGTH = 8
DEFAULT_NAME = "系统管理员"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="创建/重置管理员账号")
    parser.add_argument("--phone", help="登录手机号，同时作为后台用户名")
    parser.add_argument("--name", help="显示名；新建时默认「系统管理员」，重置时不传则保留原名")
    parser.add_argument("--password", help="不传则交互输入（推荐，避免留痕）")
    parser.add_argument("--station", type=int, default=1, help="所属站点 ID，默认 1")
    parser.add_argument("--reset", action="store_true", help="已存在时重置密码并提权为管理员")
    return parser.parse_args()


def read_password(given: str | None) -> str:
    password = given or getpass.getpass("管理员密码: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"密码至少 {MIN_PASSWORD_LENGTH} 位")
    if given is None and getpass.getpass("再次输入: ") != password:
        raise SystemExit("两次输入不一致")
    return password


def main() -> int:
    args = parse_args()
    phone = args.phone or input("登录手机号: ").strip()
    if not phone:
        raise SystemExit("手机号不能为空")
    password = read_password(args.password)

    # 脚本场景强制迁到 head：不受 AUTO_MIGRATE 开关影响（生产通常为 false），
    # 否则新库上会因表不存在而报 ProgrammingError
    run_migrations()

    with SessionLocal() as db:
        # 空库（AUTO_SEED=false）时站点还没建：不写非法外键，置空即可
        station_id: int | None = args.station
        if db.get(Station, args.station) is None:
            print(f"[warn] 站点 {args.station} 不存在，该管理员将不归属任何站点")
            station_id = None

        user = db.scalars(select(User).where(User.phone == phone)).first()
        if user is None:
            user = User(
                phone=phone,
                name=args.name or DEFAULT_NAME,
                role=Role.ADMIN,
                status=UserStatus.ACTIVE,
                station_id=station_id,
                password_hash=hash_password(password),
            )
            db.add(user)
            db.commit()
            print(f"[ok] 已创建管理员 {phone}（id={user.id}）")
            return 0

        if not args.reset:
            print(f"[skip] {phone} 已存在（角色 {user.role}），加 --reset 可重置密码并提权为管理员")
            return 1

        user.role = Role.ADMIN
        user.status = UserStatus.ACTIVE
        user.password_hash = hash_password(password)
        if station_id is not None:
            user.station_id = station_id
        # 只在显式传了 --name 时才改名：避免 --reset 顺手把已有管理员改成默认名
        if args.name:
            user.name = args.name
        db.commit()
        print(f"[ok] 已重置管理员 {phone}（id={user.id}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
