# Mercury Code (merco) 架构文档

## 目录结构

```
merco/
├── core/           # 核心引擎
├── tools/          # 工具系统
├── skills/         # 技能系统
├── memory/         # 记忆系统
├── hooks/          # 钩子系统
├── sandbox/        # 沙箱环境
├── scheduler/      # 定时任务
├── observability/  # 可观测性
├── gateway/        # 消息网关
└── utils/          # 工具函数
```

## 核心模块

### Core (核心引擎)

- **agent.py** - Agent 主循环与工具调度
- **session.py** - 会话管理与持久化
- **message.py** - 消息格式化与处理
- **context.py** - 上下文窗口管理与压缩
- **config.py** - 多层级配置系统

### Tools (工具系统)

采用注册中心模式，每个工具独立实现：

- **registry.py** - 中央工具注册表
- **base.py** - 工具基类
- **file_tools.py** - 文件读写操作
- **bash_tools.py** - 终端命令执行
- **web_tools.py** - 网络搜索与抓取
- **task_tools.py** - 子代理任务委派
- **mcp_tools.py** - MCP 协议集成

### Skills (技能系统)

- **loader.py** - 从文件系统加载 SKILL.md
- **registry.py** - 技能注册与检索
- **builtin/** - 内置技能目录

### Memory (记忆系统)

- **store.py** - JSON 文件持久化存储
- **recall.py** - 基于上下文的记忆召回
- **compressor.py** - 对话历史压缩
- **search.py** - SQLite FTS5 全文搜索

### Hooks (钩子系统)

事件驱动的钩子注册：

- **registry.py** - 钩子注册与触发
- **lifecycle.py** - 生命周期钩子
- **tool_hooks.py** - 工具执行钩子
- **chat_hooks.py** - 聊天相关钩子

### Sandbox (沙箱)

- **permissions.py** - 权限控制（allow/ask/deny）
- **isolation.py** - 执行环境隔离
- **security.py** - 安全检查

### Scheduler (定时任务)

- **cron.py** - Cron 表达式调度器
- **jobs.py** - 任务管理
- **delivery.py** - 结果投递

### Observability (可观测性)

- **logger.py** - 结构化日志
- **metrics.py** - 指标收集
- **tracing.py** - 链路追踪
- **audit.py** - 审计日志

### Gateway (消息网关)

- **base.py** - 网关基类
- **telegram.py** - Telegram 集成
- **discord.py** - Discord 集成
- **web.py** - Web 界面

## 数据流

```
用户输入 → CLI/Gateway → Agent Loop
                              ↓
                         Context Manager
                              ↓
                         LLM API Call
                              ↓
                    ┌─────────┴─────────┐
                    ↓                   ↓
              直接回复            工具调用
                                    ↓
                              Tool Registry
                                    ↓
                              执行结果 → 记忆存储
                                    ↓
                              返回 Agent Loop
```

## 扩展指南

### 添加新工具

1. 继承 `BaseTool`
2. 实现 `execute()` 方法
3. 注册到 `ToolRegistry`

### 添加新技能

1. 在 `skills/` 或 `~/.config/merco/skills/` 创建目录
2. 添加 `SKILL.md` 文件（含 frontmatter）
3. Agent 启动时自动加载

### 添加新网关

1. 继承 `BaseGateway`
2. 实现 `start()`, `stop()`, `send_message()`
3. 在配置中启用
