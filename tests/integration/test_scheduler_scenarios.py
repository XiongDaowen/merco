"""调度器集成测试 — 覆盖 cron 任务调度、并发、异常隔离。"""
import asyncio
import pytest
from datetime import datetime


class TestJobScheduling:
    @pytest.mark.asyncio
    async def test_wildcard_cron_matches_any_time(self, scenario):
        call_count = {"n": 0}

        async def handler():
            call_count["n"] += 1

        scenario.scheduler.add_job("anytime", "* * * * *", handler)

        await scenario.scheduler._check_jobs()

        assert call_count["n"] == 1

    @pytest.mark.asyncio
    async def test_job_executes_on_schedule(self, scenario):
        executed = {"n": 0}

        async def handler():
            executed["n"] += 1

        now = datetime.now()
        cron_expr = f"{now.minute} {now.hour} * * *"
        scenario.scheduler.add_job("test_job", cron_expr, handler)

        await scenario.scheduler._check_jobs()

        assert executed["n"] == 1
        job = scenario.scheduler._jobs["test_job"]
        assert job.run_count == 1
        assert job.last_run is not None


class TestHandlerTypes:
    @pytest.mark.asyncio
    async def test_async_handler_awaited(self, scenario):
        executed = {"n": 0}

        async def async_handler():
            await asyncio.sleep(0.01)
            executed["n"] += 1

        scenario.scheduler.add_job("async_job", "* * * * *", async_handler)
        await scenario.scheduler._check_jobs()
        assert executed["n"] == 1

    @pytest.mark.asyncio
    async def test_sync_handler_called(self, scenario):
        executed = {"n": 0}

        def sync_handler():
            executed["n"] += 1

        scenario.scheduler.add_job("sync_job", "* * * * *", sync_handler)
        await scenario.scheduler._check_jobs()
        assert executed["n"] == 1


class TestConcurrentExecution:
    @pytest.mark.asyncio
    async def test_multiple_jobs_concurrent_execution(self, scenario):
        results = []

        async def handler_a(): results.append("a")
        async def handler_b(): results.append("b")
        async def handler_c(): results.append("c")

        scenario.scheduler.add_job("a", "* * * * *", handler_a)
        scenario.scheduler.add_job("b", "* * * * *", handler_b)
        scenario.scheduler.add_job("c", "* * * * *", handler_c)

        await scenario.scheduler._check_jobs()
        assert sorted(results) == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_jobs_update_independently(self, scenario):
        async def h(): pass

        scenario.scheduler.add_job("j1", "* * * * *", h)
        scenario.scheduler.add_job("j2", "* * * * *", h)

        await scenario.scheduler._check_jobs()
        await scenario.scheduler._check_jobs()

        assert scenario.scheduler._jobs["j1"].run_count == 2
        assert scenario.scheduler._jobs["j2"].run_count == 2


class TestExceptionIsolation:
    @pytest.mark.asyncio
    async def test_failing_job_does_not_block_others(self, scenario):
        succeeded = {"n": 0}

        def failing_handler():
            raise RuntimeError("task failed")

        async def working_handler():
            succeeded["n"] += 1

        scenario.scheduler.add_job("failing", "* * * * *", failing_handler)
        scenario.scheduler.add_job("working", "* * * * *", working_handler)

        await scenario.scheduler._check_jobs()

        assert succeeded["n"] == 1
        assert scenario.scheduler._jobs["failing"].last_run is None
        assert scenario.scheduler._jobs["failing"].run_count == 0


class TestJobEnableDisable:
    @pytest.mark.asyncio
    async def test_disabled_job_skipped(self, scenario):
        executed = {"n": 0}

        async def handler():
            executed["n"] += 1

        scenario.scheduler.add_job("disabled_job", "* * * * *", handler)
        scenario.scheduler._jobs["disabled_job"].enabled = False

        await scenario.scheduler._check_jobs()
        assert executed["n"] == 0

    @pytest.mark.asyncio
    async def test_re_enabled_job_runs(self, scenario):
        executed = {"n": 0}

        async def handler():
            executed["n"] += 1

        scenario.scheduler.add_job("toggle_job", "* * * * *", handler)
        job = scenario.scheduler._jobs["toggle_job"]
        job.enabled = False
        await scenario.scheduler._check_jobs()
        assert executed["n"] == 0

        job.enabled = True
        await scenario.scheduler._check_jobs()
        assert executed["n"] == 1


class TestJobListRemove:
    def test_list_jobs_returns_metadata(self, scenario):
        async def h(): pass

        scenario.scheduler.add_job("j1", "* * * * *", h)
        scenario.scheduler.add_job("j2", "0 0 * * *", h)

        jobs = scenario.scheduler.list_jobs()
        names = {j["name"] for j in jobs}
        assert names == {"j1", "j2"}
        for job in jobs:
            assert "schedule" in job
            assert "enabled" in job

    def test_remove_job(self, scenario):
        async def h(): pass

        scenario.scheduler.add_job("to_remove", "* * * * *", h)
        assert "to_remove" in scenario.scheduler._jobs

        scenario.scheduler.remove_job("to_remove")
        assert "to_remove" not in scenario.scheduler._jobs

        scenario.scheduler.remove_job("nonexistent")
