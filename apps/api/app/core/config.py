from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 仅供本地开发使用的占位密钥，生产环境必须通过环境变量覆盖。
DEV_JWT_SECRET = "dev-secret-change-me-please-use-32-bytes-minimum"

# 锚定到项目根的 .env，而不是当前工作目录：
# 从别处启动（systemd、cron、IDE 不同 cwd）时不会静默退化成代码默认值。
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 应用 ---
    app_name: str = "社区养老服务管家 API"
    app_env: Literal["dev", "staging", "prod"] = "dev"
    app_version: str = "0.2.0"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- 数据库 ---
    # 只支持 PostgreSQL：JSONB、pgvector、ON CONFLICT 都是业务前提，不提供其它方言兜底。
    # 无默认值 = 必须由 .env / 环境变量显式提供，缺配置时启动即报错，不会静默连到别处。
    database_url: str

    # --- 认证 ---
    jwt_secret: str = DEV_JWT_SECRET
    jwt_expire_minutes: int = 60 * 24
    allow_demo_login: bool = True

    # --- 业务参数（集中管理，避免散落在代码里的魔法值）---
    business_timezone: str = "Asia/Shanghai"
    default_station_id: int = 1
    deposit_ratio: float = 0.3
    seed_admin_password: str = "Admin123!"

    # --- 启动行为 ---
    auto_seed: bool = True
    # 启动时自动执行 alembic upgrade head；关闭后由运维手动迁移
    auto_migrate: bool = True

    # --- 文件存储 ---
    upload_dir: str = "./uploads"
    upload_max_bytes: int = 5 * 1024 * 1024
    storage_provider: Literal["local", "minio"] = "local"
    # proxy：后端转发字节流（可鉴权、可审计）；redirect：302 到对象存储直链（不占 API 带宽）
    file_delivery: Literal["proxy", "redirect"] = "redirect"
    # 移动端图片以 <img src> 直连，默认关闭鉴权以保持兼容；生产建议开启。
    require_file_auth: bool = False

    # --- MinIO / S3 兼容对象存储 ---
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "socialoldcare-media"
    minio_secure: bool = False
    minio_region: str = "us-east-1"
    # 浏览器可达的基础地址；留空则按 endpoint/bucket 推导
    minio_public_base_url: str = ""

    # --- 外部渠道 ---
    online_payment_provider: Literal["mock", "wechat"] = "mock"
    notification_provider: Literal["db"] = "db"

    # --- 派单 ---
    # 关闭后候选接口直接返回 503，前端回退到手工员工列表
    candidate_ranking_enabled: bool = True

    # --- 异常巡检 ---
    # 关闭后 worker 跳过扫描、异常巡检接口返回 503、前端隐藏入口
    anomaly_scan_enabled: bool = True
    anomaly_scan_interval_minutes: int = 10
    anomaly_pending_confirm_minutes: int = 120
    anomaly_confirmed_unassigned_minutes: int = 60
    anomaly_assigned_not_accepted_minutes: int = 30
    anomaly_in_service_overrun_minutes: int = 60
    anomaly_balance_due_hours: int = 24

    # --- Agent（预留，暂未启用）---
    agent_enabled: bool = False
    llm_provider: str = "openai_compatible"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = 60.0

    # --- 微信 ---
    wechat_appid: str = ""
    wechat_secret: str = ""

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql"):
            raise ValueError(
                "DATABASE_URL 必须是 PostgreSQL 连接串（postgresql+psycopg://…），本项目不支持其它数据库"
            )
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def minio_public_base(self) -> str:
        """浏览器可直接访问的「域名 + 桶名」前缀。"""
        if self.minio_public_base_url:
            return self.minio_public_base_url.rstrip("/")
        scheme = "https" if self.minio_secure else "http"
        return f"{scheme}://{self.minio_endpoint}/{self.minio_bucket}"

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        if not 0 < self.deposit_ratio < 1:
            raise ValueError("deposit_ratio 必须位于 (0, 1) 区间")
        if self.storage_provider == "minio":
            missing = [
                name
                for name, value in (
                    ("MINIO_ENDPOINT", self.minio_endpoint),
                    ("MINIO_ACCESS_KEY", self.minio_access_key),
                    ("MINIO_SECRET_KEY", self.minio_secret_key),
                    ("MINIO_BUCKET", self.minio_bucket),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"STORAGE_PROVIDER=minio 时必须配置：{', '.join(missing)}")
        if self.is_prod:
            if self.allow_demo_login:
                raise ValueError("生产环境必须关闭 ALLOW_DEMO_LOGIN")
            if self.auto_seed:
                raise ValueError("生产环境必须关闭 AUTO_SEED")
            if self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32:
                raise ValueError("生产环境 JWT_SECRET 必须为不少于 32 字节的随机值")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
