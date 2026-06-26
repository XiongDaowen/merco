"""Plugin base class + PluginContext"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from merco.hooks.registry import HookRegistry
    from merco.tools.registry import ToolRegistry
    from merco.core.agent import PromptBuilder, PromptChunk
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
    from merco.sandbox.guard import PolicyPipeline
    from typing import Callable


class Plugin(ABC):
    """merco plugin base class"""
    name: str = ""           # unique identifier
    version: str = ""        # semantic version
    description: str = ""    # one-line description

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
        observer: "Observer",
        todo_manager: "TodoManager" = None,
        sub_agent_manager: "SubAgentManager" = None,
        context_pipeline: "ContextPipeline" = None,
        agent_profiles: "AgentProfileRegistry" = None,
        memory_backends: "MemoryBackendRegistry" = None,
        security_pipeline: "PolicyPipeline" = None,
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
        self.security_pipeline = security_pipeline

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
        """Add a processor to the specified pipeline"""
        pipeline = getattr(self, pipeline_name, None)
        if pipeline and hasattr(pipeline, 'use'):
            pipeline.use(processor)

    def add_recaller(self, recaller: "BaseRecaller") -> None:
        """Add a memory recaller"""
        self.recaller.add(recaller)
