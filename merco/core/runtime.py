"""AgentRuntime - 生命周期宿主：owns Agent + CronScheduler + GatewayRegistry。

薄宿主，不接管 agent turn-loop（那留在 agent.py）。CLI 构造 -> start()
（Agent.create + 插件激活 + scheduler/gateway 启动）-> REPL/submit/handle_inbound
-> stop()。start()/stop() 幂等。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from merco.core.agent import Agent
from merco.core.config import MercoConfig

if TYPE_CHECKING:
    from merco.gateway.registry import GatewayRegistry
    from merco.scheduler.cron import CronScheduler

logger = logging.getLogger("merco.core.runtime")


class AgentRuntime:
    """生命周期宿主：owns Agent + CronScheduler + GatewayRegistry。

    薄宿主——不接管 agent turn-loop（留在 agent.py）。start()/stop() 幂等。
    per-run 生命周期事件（session.create/agent.start/agent.stop/session.destroy）
    由 ``Agent.run`` 自行 emit，宿主不再额外触发——宿主 teardown 只收尾 gateway 与
    scheduler 基础设施，不属于一次 run。
    """

    def __init__(self, config: MercoConfig, *, tool_registry=None, agent: Agent | None = None):
        self.config = config
        self._tool_registry = tool_registry
        self._agent: Agent | None = agent
        self.scheduler: CronScheduler | None = None
        self.gateway_registry: GatewayRegistry | None = None
        self._scheduler_task: asyncio.Task | None = None
        self._started = False

    @property
    def agent(self) -> Agent:
        """已启动的 Agent；start() 前访问抛 RuntimeError。"""
        if self._agent is None:
            raise RuntimeError("AgentRuntime not started; call await runtime.start() first")
        return self._agent

    async def start(self) -> None:
        """激活宿主：必要时 Agent.create，绑定 inbound handler，起 gateway + scheduler。"""
        if self._started:
            return
        # 1. 若 agent 未传入：Agent.create（触发插件两阶段激活；ctx.scheduler /
        #    ctx.gateway_registry 就位）
        if self._agent is None:
            self._agent = await Agent.create(self.config, self._tool_registry)
        ctx = self._agent.plugin_ctx
        self.scheduler = ctx.scheduler
        self.gateway_registry = ctx.gateway_registry
        # 2. 绑 inbound handler + 起 gateway
        if self.gateway_registry is not None:
            self.gateway_registry.set_inbound_handler(self.handle_inbound)
            await self.gateway_registry.start_all()
        else:
            logger.warning("No gateway_registry on ctx; gateway subsystem disabled")
        # 3. 起 scheduler（start() 是阻塞 while 循环，create_task 后台跑）
        if self.scheduler is not None:
            self._scheduler_task = asyncio.create_task(self._run_scheduler())
        else:
            logger.warning("No scheduler on ctx; cron subsystem disabled")
        self._started = True

    async def _run_scheduler(self) -> None:
        """后台跑 CronScheduler.start()（阻塞 while 循环）；取消/崩溃都吞掉日志。"""
        try:
            await self.scheduler.start()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("CronScheduler.start() crashed")

    async def stop(self) -> None:
        """收尾宿主：gateway -> scheduler -> scheduler task。幂等；不 emit agent 事件。"""
        if not self._started:
            return
        # 1. gateway 收尾
        if self.gateway_registry is not None:
            try:
                await self.gateway_registry.stop_all()
            except Exception:
                logger.exception("gateway_registry.stop_all() failed")
        # 2. scheduler 收尾
        if self.scheduler is not None:
            try:
                await self.scheduler.stop()
            except Exception:
                logger.exception("scheduler.stop() failed")
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except (asyncio.CancelledError, Exception):
                pass
            self._scheduler_task = None
        self._started = False

    async def submit(self, prompt: str) -> str:
        """编程式 / cron job 入口 -> agent.run(prompt)。"""
        return await self.agent.run(prompt)

    async def handle_inbound(self, source: str, chat_id: str, message: str) -> str:
        """gateway 入口 -> agent.run(message) -> reply。

        Wave 3 单 session（见 spec §6）：chat_id 保留前向兼容，不做 per-chat_id 隔离。
        """
        return await self.agent.run(message)
