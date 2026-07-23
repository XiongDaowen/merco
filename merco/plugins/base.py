"""Plugin base class + PluginContext"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from merco.hooks.registry import HookRegistry
    from merco.tools.registry import ToolRegistry
    from merco.core.agent import PromptBuilder, PromptChunk, Agent
    from merco.core.pipeline import RecoveryPipeline, ResultPipeline
    from merco.memory.save_pipeline import MemorySavePipeline
    from merco.memory.recall import HybridRecaller, BaseRecaller
    from merco.core.config import MercoConfig
    from merco.observability.observer import Observer
    from merco.tools.base import BaseTool
    from merco.todo.manager import TodoManager
    from merco.agents.profile import AgentProfileRegistry
    from merco.agents.subagent import SubAgentManager
    from merco.context.pipeline import ContextPipeline
    from merco.memory.backend import MemoryBackendRegistry
    from merco.core.loop_policy import LoopPolicyRegistry
    from merco.skills.registry import SkillRegistry
    from merco.mcp.manager import MCPServerManager
    from merco.scheduler.cron import CronScheduler
    from merco.sandbox.guard import PolicyPipeline as PermissionPipeline
    from merco.core.llm.registry import ModelRegistry
    from merco.core.llm.base import ModelProviderInfo
    from merco.gateway.base import GatewayAdapter
    from merco.gateway.registry import GatewayRegistry


_PIPELINE_WHITELIST = {
    "result_pipeline",
    "recovery_pipeline",
    "memory_save_pipeline",
    "context_pipeline",
}


class Plugin(ABC):
    """merco plugin base class"""
    name: str = ""           # unique identifier
    version: str = ""        # semantic version
    description: str = ""    # one-line description
    priority: int = 50       # 越大越早激活；>= BOOT_PRIORITY(100) 在 boot 阶段激活
    depends_on: list[str] = []  # 必须先激活的插件名

    @abstractmethod
    async def activate(self, ctx: "PluginContext") -> None:
        """Called on activation; ctx provides all extension points"""
        ...

    async def deactivate(self) -> None:
        """Called on deactivation to clean up resources. Default no-op."""
        pass


class PluginContext:
    """Extension point entry for plugins, injected during activate"""

    def __init__(
        self,
        hooks: "HookRegistry",
        tool_registry: "ToolRegistry",
        prompt_builder: "PromptBuilder",
        recovery_pipeline: "RecoveryPipeline",
        result_pipeline: "ResultPipeline",
        memory_save_pipeline: "MemorySavePipeline",
        recaller: "HybridRecaller",
        config: "MercoConfig",
        observer: "Observer" = None,
        todo_manager: "TodoManager" = None,
        sub_agent_manager: "SubAgentManager" = None,
        context_pipeline: "ContextPipeline" = None,
        agent_profiles: "AgentProfileRegistry" = None,
        memory_backends: "MemoryBackendRegistry" = None,
        loop_policies: "LoopPolicyRegistry" = None,
        agent: "Agent" = None,
        skill_registry: "SkillRegistry" = None,
        mcp_manager: "MCPServerManager" = None,
        scheduler: "CronScheduler" = None,
        security_pipeline: "PermissionPipeline" = None,
        model_registry: "ModelRegistry" = None,
        gateway_registry: "GatewayRegistry" = None,
        metadata: dict = None,
    ):
        self.hooks = hooks
        self.tool_registry = tool_registry
        self.prompt_builder = prompt_builder
        self.recovery_pipeline = recovery_pipeline
        self.result_pipeline = result_pipeline
        self.memory_save_pipeline = memory_save_pipeline
        self.recaller = recaller
        self.config = config
        self.observer = observer
        self.todo_manager = todo_manager
        self.sub_agent_manager = sub_agent_manager
        self.context_pipeline = context_pipeline
        self.agent_profiles = agent_profiles
        self.memory_backends = memory_backends
        self.loop_policies = loop_policies
        self.agent = agent
        self.skill_registry = skill_registry
        self.mcp_manager = mcp_manager
        self.scheduler = scheduler
        self.security_pipeline = security_pipeline
        self.model_registry = model_registry
        self.gateway_registry = gateway_registry
        self.metadata = metadata if metadata is not None else {}

    def on(self, event: str, handler: "Callable") -> None:
        """Subscribe to event (convenience method)"""
        self.hooks.on(event, handler)

    def register_tool(self, tool: "BaseTool") -> None:
        """Register a tool"""
        self.tool_registry.register(tool)

    def add_prompt_chunk(self, chunk: "PromptChunk") -> None:
        """Inject a system prompt chunk"""
        self.prompt_builder.use(chunk)

    def add_processor(self, pipeline_name: str, processor) -> None:
        """加处理器到白名单管线"""
        if pipeline_name not in _PIPELINE_WHITELIST:
            raise ValueError(f"Pipeline '{pipeline_name}' not extensible")
        pipeline = getattr(self, pipeline_name, None)
        if pipeline and hasattr(pipeline, 'use'):
            pipeline.use(processor)

    def add_recaller(self, recaller: "BaseRecaller") -> None:
        """Add a memory recaller"""
        self.recaller.add(recaller)

    def register_agent_profile(self, profile) -> None:
        """注册一个 AgentProfile"""
        self.agent_profiles.register(profile)

    def register_loop_policy(self, policy) -> None:
        """注册一个 LoopPolicy"""
        self.loop_policies.register(policy)

    def add_memory_backend(self, backend) -> None:
        """添加一个 MemoryBackend"""
        self.memory_backends.register(backend)

    def add_security_policy(self, policy) -> None:
        """添加一个 PermissionPolicy 到安全策略链"""
        if self.security_pipeline is None:
            raise RuntimeError("security_pipeline not available on this context")
        self.security_pipeline.use(policy)

    def register_model_provider(self, info: "ModelProviderInfo") -> None:
        """注册一个 ModelProvider（第三方插件用）。"""
        if self.model_registry is None:
            raise RuntimeError("model_registry not available on this context")
        self.model_registry.register(info)

    def register_gateway(self, adapter: "GatewayAdapter") -> None:
        """注册一个 GatewayAdapter（第三方插件用）。"""
        if self.gateway_registry is None:
            raise RuntimeError("gateway_registry not available on this context")
        self.gateway_registry.register(adapter)


@dataclass
class PluginSpec:
    """已发现插件的元数据 + 懒加载器。discovery 产出、manager 消费。"""

    name: str
    source: str                            # "entrypoint" | "dir" | "manual"
    loader: Callable[[], type] | None = None  # 返回 Plugin 子类（懒加载）
    version: str = ""
    description: str = ""
    priority: int = 50
    depends_on: list[str] = field(default_factory=list)

    _cls: type | None = field(default=None, init=False, repr=False, compare=False)
    _instance: "Plugin | None" = field(default=None, init=False, repr=False, compare=False)

    def load_cls(self) -> type:
        """导入并返回 Plugin 子类，缓存到 _cls。"""
        if self._cls is None:
            if self.loader is None:
                raise RuntimeError(f"PluginSpec '{self.name}' has no loader")
            self._cls = self.loader()
        return self._cls

    def instantiate(self) -> "Plugin":
        """返回 Plugin 实例，缓存到 _instance。"""
        if self._instance is None:
            self._instance = self.load_cls()()
        return self._instance
