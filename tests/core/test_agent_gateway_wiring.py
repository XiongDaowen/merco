"""Agent 构造 gateway_registry + plugin_ctx accessor 测试。"""
from merco.core.agent import Agent
from merco.core.config import MercoConfig
from merco.gateway.registry import GatewayRegistry
from merco.tools.registry import ToolRegistry


def _make_agent(monkeypatch, tmp_path) -> Agent:
    monkeypatch.setattr("merco.core.agent._get_db_path", lambda: str(tmp_path / "t.db"))
    cfg = MercoConfig()
    cfg.model.api_key = "k"
    cfg.memory_path = str(tmp_path / "mem")
    return Agent(config=cfg, tool_registry=ToolRegistry())


def test_agent_constructs_gateway_registry(monkeypatch, tmp_path):
    agent = _make_agent(monkeypatch, tmp_path)
    assert isinstance(agent.gateway_registry, GatewayRegistry)
    # 初始为空（内置 WebhookGateway 由 GatewayPlugin 激活时填，非 __init__）
    assert agent.gateway_registry.list() == []


def test_plugin_ctx_property_exposes_private_ctx(monkeypatch, tmp_path):
    """plugin_ctx property 返回 _plugin_ctx（Runtime 用）。"""
    agent = _make_agent(monkeypatch, tmp_path)
    assert agent.plugin_ctx is agent._plugin_ctx


def test_plugin_ctx_gateway_registry_is_agent_gateway_registry(monkeypatch, tmp_path):
    """ctx.gateway_registry 与 agent.gateway_registry 是同一对象。"""
    agent = _make_agent(monkeypatch, tmp_path)
    assert agent.plugin_ctx.gateway_registry is agent.gateway_registry
