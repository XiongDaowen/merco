# 🧠 merco — Mercury Code

> Mer(cury) + Co(de) = **默客** — 默默写代码的 AI 伙伴。轻量、高效、可落地的 Python 智能开发助手。

**Phase 2 深入** — Agent 核心循环 + 工具系统 + CLI 交互 + Session 持久化 + 可观察性 + 安全守卫。

## 快速开始

```bash
# 安装
pip install merco
# 或
uv tool install merco

# 交互式配置（一分钟搞定）
merco setup

# 启动
merco
```

> 也支持手动配置：`~/.config/merco/config.json` 或项目目录 `./merco.json`

## 当前功能

- **REPL 交互**: 进度条、上下文用量、会话管理、历史恢复
- **Agent 循环**: 用户输入 → LLM → 工具调用 → 循环，tool call + result 完整链路持久化
- **工具**: `bash`、`read_file`(流式+翻页)、`write_file`、`edit_file`(SEARCH/REPLACE+diff)、`web_fetch`
- **LLM 客户端**: OpenAI 兼容接口，5 平台预置(MiniMax/OpenAI/Anthropic/OpenRouter/DeepSeek)，自定义 base_url
- **交互式配置**: `merco setup` 引导选平台→填 key→选模型
- **Session 持久化**: SQLite WAL，启动自动恢复，`/sessions` 列表+切换，`/new` 新会话
- **安全守卫**: `ToolGuard` 敏感命令执行前确认，30 条默认规则，可自定义
- **可观察性**: `/report` 显示 token 统计、LLM 延迟、工具分布、缓存命中率
- **Skill 系统**: 自动注入相关项目文档，手动 `skill_view` 加载
- **Diff 预览**: `edit_file` 执行前展示左右对照 diff，支持 `sandbox_mode: show` 自动应用

## REPL 命令

```
/new       新会话
/sessions  历史会话列表+切换
/report    会话统计报告
/model     当前模型
/context   上下文用量
/tools     可用工具
/skills    已加载技能
/help      帮助
/exit      退出
```

## 配置项

配置文件路径: `~/.config/merco/config.json` 或项目目录 `./merco.json`

### 流式输出配置

- `stream_thinking`: 是否启用 thinking 流式输出（默认: `true`）
- `stream_content`: 是否启用 content 流式输出（默认: `true`）
- `stream_thinking_transient`: thinking 框是否在结束后消失（默认: `false`，即保留思考面板）
- `stream_render_interval`: 流式 reasoning 面板最小渲染间隔，单位秒（默认: `0.3`，0 = 不限制）

示例:

```json
{
  "stream_content": true,
  "stream_thinking_transient": false
}
```

## 架构

| 层 | 状态 | 说明 |
|----|------|------|
| `core/` | 🟢 POLISHED | Agent 循环 + LLM + 配置 + Session 持久化 |
| `tools/` | 🟢 POLISHED | Bash + 文件读写 + SEARCH/REPLACE diff + 注册中心 |
| `skills/` | 🟢 可用 | Skill 加载/注册/检索 + 自动注入 |
| `sandbox/` | 🟢 POLISHED | Diff split view + show mode + ToolGuard 守卫 |
| `observability/` | 🟢 已接线 | hooks 驱动 Observer，`/report` 命令 |
| `hooks/` | 🟢 已接线 | Agent 关键节点 emit 事件 |
| `memory/` | 🟡 部分 | SQLite Session 持久化，搜索/压缩待完善 |
| `scheduler/` | 🔴 未激活 | Cron 实现完整，CLI 未启动 |
| `gateway/` | 🔴 骨架 | 多平台网关占位 |
| `cli/` | 🟢 POLISHED | REPL + Dashboard + PromptDecorator 可组合 |
| `web/` | 🟡 部分 | FastAPI 占位 |

## 项目文档

详细进展、架构、决策、教训、Bug 追踪见 `docs/project-vision/`。

## 许可证

MIT
