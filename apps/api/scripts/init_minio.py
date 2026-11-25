"""初始化 MinIO：建桶 + 设置匿名只读策略。

用法：
    .venv/bin/python scripts/init_minio.py            # 建桶并开放匿名读（图片可直连展示）
    .venv/bin/python scripts/init_minio.py --private  # 只建桶，保持私有（配合 FILE_DELIVERY=proxy）

配置来自 .env 的 MINIO_* 变量。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from minio import Minio

from app.core.config import settings
from app.infra.storage import public_read_only_policy


def main() -> int:
    if not (settings.minio_endpoint and settings.minio_access_key and settings.minio_secret_key):
        print("请先在 .env 中配置 MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY")
        return 1

    bucket = settings.minio_bucket
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
        region=settings.minio_region or None,
    )

    if client.bucket_exists(bucket):
        print(f"[skip] 桶已存在：{bucket}")
    else:
        client.make_bucket(bucket)
        print(f"[ok] 已创建桶：{bucket}")

    if "--private" in sys.argv:
        print("[ok] 保持私有桶，读取走 API 代理（FILE_DELIVERY=proxy）")
    else:
        client.set_bucket_policy(bucket, json.dumps(public_read_only_policy(bucket)))
        print(f"[ok] 已设置匿名只读策略（仅 s3:GetObject）：{bucket}")
        print(f"     图片直链前缀：{settings.minio_public_base}/<key>")

    print(f"[done] endpoint={settings.minio_endpoint} bucket={bucket}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
