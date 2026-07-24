"""Cron 调度器"""

import asyncio
import logging
from datetime import datetime
from typing import Callable

logger = logging.getLogger("merco.scheduler.cron")


class CronJob:
    """定时任务"""

    def __init__(self, name: str, schedule: str, handler: Callable):
        self.name = name
        self.schedule = schedule  # cron 表达式
        self.handler = handler
        self.enabled = True
        self.last_run = None
        self.run_count = 0


class CronScheduler:
    """Cron 表达式调度器"""

    def __init__(self):
        self._jobs: dict[str, CronJob] = {}
        self._running = False

    def add_job(self, name: str, schedule: str, handler: Callable):
        """添加定时任务"""
        self._jobs[name] = CronJob(name, schedule, handler)

    def remove_job(self, name: str):
        """移除定时任务"""
        self._jobs.pop(name, None)

    def list_jobs(self) -> list[dict]:
        """列出所有任务"""
        return [
            {
                "name": job.name,
                "schedule": job.schedule,
                "enabled": job.enabled,
                "last_run": job.last_run,
                "run_count": job.run_count,
            }
            for job in self._jobs.values()
        ]

    async def start(self):
        """启动调度器"""
        self._running = True
        while self._running:
            await self._check_jobs()
            await asyncio.sleep(60)  # 每分钟检查

    async def stop(self):
        """停止调度器"""
        self._running = False

    async def _check_jobs(self):
        """检查并执行到期任务"""
        now = datetime.now()
        for job in self._jobs.values():
            if job.enabled and self._is_due(job.schedule, now):
                await self._run_job(job)

    async def _run_job(self, job: CronJob):
        """执行单个任务。

        handler 抛异常时记 ERROR 日志（保留 traceback），但不向上抛，
        以免打断其他任务或调度循环；失败时不推进 last_run / run_count。
        """
        try:
            if asyncio.iscoroutinefunction(job.handler):
                await job.handler()
            else:
                job.handler()
            job.last_run = datetime.now()
            job.run_count += 1
        except Exception:
            logger.exception("Cron job %r failed", job.name)

    @staticmethod
    def _is_due(schedule: str, now: datetime) -> bool:
        """检查 cron 表达式是否匹配当前时间。

        仅支持 ``*`` 与精确整数值。

        不支持（完整 cron 解析超出当前范围，YAGNI）：
        - 范围，如 ``1-5``
        - 列表，如 ``1,3,5``
        - 步长，如 ``*/5``

        weekday 字段采用 cron 约定：``0=周日..6=周六``，
        而非 Python ``datetime.weekday()`` 的 ``0=周一..6=周日``。
        """
        parts = schedule.split()
        if len(parts) != 5:
            return False

        minute, hour, day, month, weekday = parts

        def match(part, value):
            if part == "*":
                return True
            return str(value) == part

        # cron weekday: 0=周日..6=周六；Python weekday(): 0=周一..6=周日
        cron_wday = (now.weekday() + 1) % 7

        return (
            match(minute, now.minute)
            and match(hour, now.hour)
            and match(day, now.day)
            and match(month, now.month)
            and match(weekday, cron_wday)
        )
