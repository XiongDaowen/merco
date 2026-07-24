"""Cron调度器单元测试"""

import asyncio
import logging
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from merco.scheduler.cron import CronJob, CronScheduler


class TestCronJob:
    """CronJob测试"""

    def test_job_creation(self):
        """测试任务创建"""
        handler = MagicMock()
        job = CronJob("test_job", "* * * * *", handler)

        assert job.name == "test_job"
        assert job.schedule == "* * * * *"
        assert job.handler == handler
        assert job.enabled is True
        assert job.last_run is None
        assert job.run_count == 0


class TestCronScheduler:
    """CronScheduler测试"""

    @pytest.fixture
    def scheduler(self):
        """创建调度器实例"""
        return CronScheduler()

    @pytest.fixture
    def mock_handler(self):
        """模拟任务处理器"""
        return MagicMock()

    def test_add_job(self, scheduler, mock_handler):
        """测试添加任务"""
        scheduler.add_job("test_job", "* * * * *", mock_handler)

        assert "test_job" in scheduler._jobs
        job = scheduler._jobs["test_job"]
        assert job.name == "test_job"
        assert job.schedule == "* * * * *"
        assert job.handler == mock_handler

    def test_remove_job(self, scheduler, mock_handler):
        """测试移除任务"""
        scheduler.add_job("test_job", "* * * * *", mock_handler)
        assert "test_job" in scheduler._jobs

        scheduler.remove_job("test_job")
        assert "test_job" not in scheduler._jobs

        # 移除不存在的任务不报错
        scheduler.remove_job("nonexistent_job")

    def test_list_jobs(self, scheduler, mock_handler):
        """测试列出任务"""
        # 空列表
        assert scheduler.list_jobs() == []

        # 添加任务
        scheduler.add_job("job1", "* * * * *", mock_handler)
        scheduler.add_job("job2", "0 0 * * *", mock_handler)
        # 禁用一个任务
        scheduler._jobs["job2"].enabled = False

        jobs = scheduler.list_jobs()
        assert len(jobs) == 2
        job_names = [j["name"] for j in jobs]
        assert "job1" in job_names
        assert "job2" in job_names
        assert jobs[job_names.index("job1")]["enabled"] is True
        assert jobs[job_names.index("job2")]["enabled"] is False

    @pytest.mark.asyncio
    async def test_start_stop(self, scheduler):
        """测试启动和停止调度器"""

        # 启动后立即停止，防止一直运行
        async def stop_after_short_delay():
            await asyncio.sleep(0.1)
            await scheduler.stop()

        # 同时运行调度器和停止任务
        await asyncio.gather(scheduler.start(), stop_after_short_delay())

        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_check_jobs_runs_due_jobs(self, scheduler, mock_handler):
        """测试检查任务时执行到期的任务"""
        # 添加一个每分钟执行的任务
        scheduler.add_job("test_job", "* * * * *", mock_handler)
        job = scheduler._jobs["test_job"]

        # mock当前时间，让任务到期
        now = datetime(2024, 1, 1, 12, 0, 0)  # 中午12点整
        with patch("merco.scheduler.cron.datetime") as mock_datetime:
            mock_datetime.now.return_value = now
            mock_datetime.fromtimestamp = datetime.fromtimestamp

            await scheduler._check_jobs()

            # 任务应该被执行一次
            assert mock_handler.call_count == 1
            assert job.last_run == now
            assert job.run_count == 1

    @pytest.mark.asyncio
    async def test_check_jobs_skips_disabled_jobs(self, scheduler, mock_handler):
        """测试禁用的任务不会被执行"""
        scheduler.add_job("test_job", "* * * * *", mock_handler)
        job = scheduler._jobs["test_job"]
        job.enabled = False

        now = datetime(2024, 1, 1, 12, 0, 0)
        with patch("merco.scheduler.cron.datetime") as mock_datetime:
            mock_datetime.now.return_value = now

            await scheduler._check_jobs()

            # 任务不应该被执行
            assert mock_handler.call_count == 0
            assert job.last_run is None
            assert job.run_count == 0

    @pytest.mark.asyncio
    async def test_check_jobs_skips_not_due_jobs(self, scheduler, mock_handler):
        """测试不到期的任务不会被执行"""
        # 任务只在1点执行
        scheduler.add_job("test_job", "0 1 * * *", mock_handler)

        # 当前时间是12点，任务不到期
        now = datetime(2024, 1, 1, 12, 0, 0)
        with patch("merco.scheduler.cron.datetime") as mock_datetime:
            mock_datetime.now.return_value = now

            await scheduler._check_jobs()

            # 任务不应该被执行
            assert mock_handler.call_count == 0

    @pytest.mark.asyncio
    async def test_run_job_async_handler(self, scheduler):
        """测试执行异步处理器"""
        mock_handler = MagicMock()

        # 模拟异步函数
        async def async_handler():
            mock_handler()

        job = CronJob("async_job", "* * * * *", async_handler)

        await scheduler._run_job(job)

        assert mock_handler.call_count == 1
        assert job.last_run is not None
        assert job.run_count == 1

    @pytest.mark.asyncio
    async def test_run_job_sync_handler(self, scheduler, mock_handler):
        """测试执行同步处理器"""
        job = CronJob("sync_job", "* * * * *", mock_handler)

        await scheduler._run_job(job)

        assert mock_handler.call_count == 1
        assert job.last_run is not None
        assert job.run_count == 1

    @pytest.mark.asyncio
    async def test_run_job_exception_handled(self, scheduler):
        """测试任务执行异常不会中断调度器"""

        def failing_handler():
            raise Exception("Task failed")

        job = CronJob("failing_job", "* * * * *", failing_handler)

        # 执行异常任务不应该抛出异常
        await scheduler._run_job(job)

        assert job.last_run is None  # 异常时不更新last_run
        assert job.run_count == 0  # 异常时不增加计数

    class TestIsDue:
        """_is_due方法测试"""

        def test_wildcard_matches_anything(self):
            """测试*匹配任何值"""
            now = datetime(2024, 1, 1, 12, 30, 0)  # 1月1日12点30分，周一
            assert CronScheduler._is_due("* * * * *", now) is True

        def test_exact_match(self):
            """测试精确匹配"""
            now = datetime(2024, 1, 1, 12, 30, 0)  # 1月1日12点30分，周一
            # cron weekday: 0=周日..6=周六；2024-01-01 是周一，对应 cron weekday=1
            assert CronScheduler._is_due("30 12 1 1 1", now) is True
            # 分钟不匹配
            assert CronScheduler._is_due("29 12 1 1 1", now) is False
            # 小时不匹配
            assert CronScheduler._is_due("30 13 1 1 1", now) is False
            # 日不匹配
            assert CronScheduler._is_due("30 12 2 1 1", now) is False
            # 月不匹配
            assert CronScheduler._is_due("30 12 1 2 1", now) is False
            # 星期不匹配（cron weekday=2 对应周二，当前是周一）
            assert CronScheduler._is_due("30 12 1 1 2", now) is False

        def test_invalid_cron_expression(self):
            """测试无效的cron表达式"""
            now = datetime.now()
            # 少于5个部分
            assert CronScheduler._is_due("* * * *", now) is False
            # 多于5个部分
            assert CronScheduler._is_due("* * * * * *", now) is False


# --- Wave 3 T2 regression tests -------------------------------------------------


def test_is_due_star_matches_any_time():
    """`* * * * *` 任意时刻匹配。"""
    sched = CronScheduler()
    assert sched._is_due("* * * * *", datetime(2026, 7, 23, 14, 30)) is True


def test_is_due_exact_match():
    """精确值匹配指定分时。"""
    sched = CronScheduler()
    now = datetime(2026, 7, 23, 14, 30)  # 周四
    assert sched._is_due("30 14 23 7 *", now) is True
    assert sched._is_due("31 14 23 7 *", now) is False


def test_is_due_weekday_uses_cron_sunday_zero_convention():
    """cron weekday: 0=周日..6=周六（非 Python 的 Mon=0）。

    2026-07-26 是周日。cron 表达式 "* * * * 0" 应在周日匹配，周一不匹配。
    """
    sched = CronScheduler()
    sunday = datetime(2026, 7, 26, 10, 0)  # 周日
    monday = datetime(2026, 7, 27, 10, 0)  # 周一
    assert sched._is_due("* * * * 0", sunday) is True, "周日应匹配 weekday=0"
    assert sched._is_due("* * * * 0", monday) is False, "周一不应匹配 weekday=0"


async def test_run_job_logs_exception_does_not_swallow(caplog):
    """job handler 抛异常时 _run_job 记日志，不静默吞。"""
    sched = CronScheduler()

    def bad_handler():
        raise RuntimeError("boom")

    job = CronJob("bad", "* * * * *", bad_handler)
    with caplog.at_level(logging.ERROR, logger="merco.scheduler.cron"):
        await sched._run_job(job)
    # 异常被记 ERROR 日志：logger.exception 保留 traceback (exc_info) + 消息含 job 名
    assert any(r.levelname == "ERROR" and r.exc_info is not None and "bad" in r.message for r in caplog.records), (
        "job 异常应记 ERROR 日志（含 traceback 与 job 名）"
    )
    # job 状态未推进（last_run 未更新，因 handler 失败）
    assert job.last_run is None
