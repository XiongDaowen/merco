# 🧠 merco — Mercury Code

> **Mer**(cury) + **Co**(de) = 默客 — 默默写代码的 AI 伙伴

一个轻量、高效、可落地的 Python 智能开发助手，运行在你的终端里。

---

## ✨ 特性亮点

| 功能 | 说明 |
|------|------|
| 🤖 **Agent 循环** | 用户输入 → LLM → 工具调用 → 循环，完整链路持久化 |
| 🖥️ **流式输出** | thinking/content 双面板实时显示，推理过程一目了然 |
| 🛡️ **安全守卫** | 敏感命令执行前确认，30+ 条默认规则，可自定义 |
| 💾 **Session 记忆** | SQLite WAL 持久化，自动恢复，/sessions 切换历史 |
| 🔌 **插件系统** | 可扩展的插件架构，内置 Skill/Scheduler/MCP 等插件 |
| 📊 **可观察性** | /report 显示 token 统计、LLM 延迟、工具分布 |

---

## 🚀 快速开始

```bash
# 安装
pip install merco
# 或
uv tool install merco

# 交互式配置（首次运行引导）
merco setup

# 启动
merco
```

> 也支持手动配置：`~/.config/merco/config.json` 或项目目录 `./merco.json`

---

## 📁 项目结构

```
merco/
├── agents/        # Agent 抽象 + 子 Agent
├── cli/          # REPL 命令行界面
├── context/      # 上下文管道 + 处理器
├── core/         # Agent 核心循环 + LLM + 配置
├── hooks/        # 生命周期事件
├── memory/       # Session 持久化 + 记忆召回
├── mcp/          # MCP 协议客户端
├── observability/ # 可观察性（统计/报告）
├── plugins/      # 插件系统 + 内置插件
├── sandbox/      # 安全守卫 + 快照
├── scheduler/    # 定时任务调度
├── skills/       # Skill 加载/注册/检索
├── tools/        # 工具集（Bash/文件/Web）
└── web/          # Web API（可选）
```

---

## 🗂️ REPL 命令

```
/new       新会话
/sessions  历史会话列表 + 切换
/report    会话统计报告
/model     当前模型
/context   上下文用量
/tools     可用工具
/skills    已加载技能
/help      帮助
/exit      退出
```

---

## ⚙️ 配置示例

```json
{
  "model": "claude-sonnet-4-20250514",
  "stream_thinking": true,
  "stream_content": true,
  "stream_render_interval": 0.3,
  "tool_guard_enabled": true
}
```

---

## 🏗️ 架构状态

| 模块 | 状态 | 说明 |
|------|:----:|------|
| `core/` | 🟢 | Agent 循环 + LLM + 配置 |
| `tools/` | 🟢 | Bash + 文件读写 + Web Fetch |
| `skills/` | 🟢 | 加载/注册/检索 + 自动注入 |
| `sandbox/` | 🟢 | ToolGuard + Diff 预览 |
| `observability/` | 🟢 | hooks 驱动 Observer |
| `hooks/` | 🟢 | Agent 生命周期事件 |
| `plugins/` | 🟢 | 插件管理器 + 内置插件 |
| `scheduler/` | 🟢 | Cron 定时任务 |
| `memory/` | 🟡 | Session 持久化，召回增强中 |
| `context/` | 🟡 | 上下文压缩管道 |
| `agents/` | 🟡 | Agent Profile + 子 Agent |
| `web/` | 🔴 | FastAPI 占位（未激活） |

---

## 📖 项目文档

详细进展、架构决策、经验教训见 [docs/project-vision/](docs/project-vision/)。

## 📄 许可证

MIT
