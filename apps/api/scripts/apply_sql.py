"""按文件名顺序执行某个目录下的 .sql 文件。

默认执行 ``sql/*.sql``（基础数据，幂等，可反复跑），
不会递归子目录，所以 ``sql/reset/`` 里的清库脚本必须显式指定目录才会执行。

用法：
    .venv/bin/python scripts/apply_sql.py              # 执行 sql/*.sql
    .venv/bin/python scripts/apply_sql.py sql/reset    # 执行 sql/reset/*.sql（清库，慎用）
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sql")
    if not target.is_absolute():
        target = PROJECT_ROOT / target

    files = sorted(target.glob("*.sql"))
    if not files:
        print(f"[skip] {target} 下没有 .sql 文件")
        return 1

    # 这些 SQL 用了 PG 专有语法（VALUES 列别名、now()、::jsonb、多语句），别的方言必挂
    if engine.dialect.name != "postgresql":
        print(
            f"[abort] 基础数据 SQL 使用 PG 方言，当前连接方言为 {engine.dialect.name}，请改用 PostgreSQL"
        )
        return 2

    print(f"目标库: {engine.url.database} @ {engine.url.host}:{engine.url.port}")
    with engine.begin() as conn:
        for path in files:
            conn.exec_driver_sql(path.read_text(encoding="utf-8"))
            print(f"[ok] {path.relative_to(PROJECT_ROOT)}")

    print(f"完成，共执行 {len(files)} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
