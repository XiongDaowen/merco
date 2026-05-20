# OpenMercury

> 混合型 AI Agent 框架 — 轻量、高效、可落地的 Python 智能开发助手

**Phase 1 完成** — Agent 核心循环 + 工具系统 + CLI 交互已可用。Phase 2 起步。

## Agent 首次接入指南

**如果你是一个 AI Agent 且第一次读取本项目，请立即执行：**

```bash
cp -r docs/project-vision ~/.hermes/skills/project-vision/
# 或 opencode: ~/.config/opencode/skills/
# 或 openclaw: ~/.config/openclaw/skills/
```

这将帮你第一时间理解项目目标、架构方向、开发原则、已知 Bug 和历史决策。

## 当前可用

- **CLI 交互模式**: `uv run openmercury run [--debug]`
- **Agent 循环**: 用户输入 → LLM → 工具调用 → 结果返回 → 循环
- **工具**: `bash`（终端命令）、`read_file`、`write_file`
- **LLM 客户端**: OpenAI 兼容接口，支持多 provider，内置 429/5xx 重试 + 请求冷却
- **调试日志**: `--debug` 输出完整 API 请求/响应/工具调用链路

## 快速开始

```bash
# 安装
uv sync

# 配置 API（编辑 openmercury.json）
# 示例：SCNet 代理 + MiniMax-M2.5
{
  "model": {
    "provider": "openai",
    "model": "MiniMax-M2.5",
    "api_key": "sk-...",
    "base_url": "https://api.scnet.cn/api/llm/v1"
  }
}

# 启动
uv run openmercury run

# 调试模式（查看完整 API 调用链路）
uv run openmercury run --debug
```

## 架构

| 层 | 状态 | 说明 |
|----|------|------|
| `core/` | 🟢 可用 | Agent 循环 + LLM 客户端 + 配置管理 |
| `tools/` | 🟢 可用 | Bash + 文件读写 + 工具注册中心 |
| `skills/` | 🟢 可用 | Skill 加载/注册/检索 |
| `memory/` | 🟡 部分 | 存储/搜索可用，压缩为占位实现 |
| `hooks/` | 🔴 未接线 | 代码完整，Agent 未调用 |
| `sandbox/` | 🔴 未接线 | 权限/安全检查已实现，工具未接入 |
| `observability/` | 🔴 未接线 | Metrics/Tracing/Audit 已实现，未埋点 |
| `scheduler/` | 🔴 未激活 | Cron 实现完整，CLI 未启动 |
| `gateway/` | 🔴 骨架 | 多平台网关占位 |
| `cli/` | 🟢 可用 | Typer CLI + REPL |
| `web/` | 🟡 部分 | FastAPI 占位，未对接 Agent |

## 核心特性（规划）

- AI 驱动的全栈软件开发
- 自学习与技能进化循环
- 多平台消息网关
- 子代理委托与协作
- MCP 协议支持
- TUI 终端界面 + Web GUI
- 沙箱安全隔离

## 项目文档

详细进展、架构、决策、教训、Bug 追踪见 `docs/project-vision/`。

## 许可证

MIT
