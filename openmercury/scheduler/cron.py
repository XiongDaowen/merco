"""Cron 调度器"""

import asyncio
from datetime import datetime
from typing import Callable, Awaitable


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
        """执行单个任务"""
        try:
            if asyncio.iscoroutinefunction(job.handler):
                await job.handler()
            else:
                job.handler()
            job.last_run = datetime.now()
            job.run_count += 1
        except Exception as e:
            pass  # TODO: 添加错误处理与通知

    @staticmethod
    def _is_due(schedule: str, now: datetime) -> bool:
        """检查 cron 表达式是否匹配当前时间"""
        # TODO: 实现完整的 cron 解析
        # 简化实现：支持 "* * * * *" (每分钟) 和具体数字
        parts = schedule.split()
        if len(parts) != 5:
            return False

        minute, hour, day, month, weekday = parts

        def match(part, value):
            if part == "*":
                return True
            return str(value) == part

        return (
            match(minute, now.minute)
            and match(hour, now.hour)
            and match(day, now.day)
            and match(month, now.month)
            and match(weekday, now.weekday())
        )
