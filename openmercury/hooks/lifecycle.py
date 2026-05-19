"""生命周期钩子"""

from .registry import HookRegistry


def register_lifecycle_hooks(registry: HookRegistry):
    """注册生命周期钩子"""

    @registry.on("agent.start")
    async def on_agent_start(**kwargs):
        pass

    @registry.on("agent.stop")
    async def on_agent_stop(**kwargs):
        pass

    @registry.on("session.create")
    async def on_session_create(session_id: str, **kwargs):
        pass

    @registry.on("session.destroy")
    async def on_session_destroy(session_id: str, **kwargs):
        pass
