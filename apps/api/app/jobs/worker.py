"""异常巡检 worker。

刻意不引入 Celery/APScheduler：一个循环 + 独立容器即可，
``pg_try_advisory_lock`` 保证多副本时只有一个实例真正扫描。
"""

from __future__ import annotations

import logging
import signal
import threading

from ..core.config import settings
from ..core.logging import setup_logging
from ..db.session import SessionLocal
from ..modules.audit import AuditService
from ..modules.tasks.repository import TaskRepository
from ..modules.tasks.service import TaskService

logger = logging.getLogger(__name__)

_stop = threading.Event()


def _handle_signal(signum: int, _frame: object) -> None:
    logger.info("收到信号 %s，准备退出 worker", signum)
    _stop.set()


def scan_once() -> None:
    with SessionLocal() as db:
        service = TaskService(db, TaskRepository(db), AuditService(db))
        result = service.scan(trigger="worker")
        if not result.scanned:
            logger.info("跳过本轮扫描：%s", result.skip_reason)


def main() -> None:
    setup_logging()
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    interval = max(1, settings.anomaly_scan_interval_minutes) * 60
    logger.info(
        "异常巡检 worker 启动：每 %s 秒扫描一次，开关=%s",
        interval,
        settings.anomaly_scan_enabled,
    )
    while not _stop.is_set():
        if not settings.anomaly_scan_enabled:
            # 开关关闭时不退出进程：打开后无需重启容器即可恢复
            logger.warning("ANOMALY_SCAN_ENABLED=false，本轮跳过扫描")
        else:
            try:
                scan_once()
            except Exception:
                logger.exception("异常扫描失败，等待下一轮")
        _stop.wait(interval)


if __name__ == "__main__":
    main()
