# 关键决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-20 | 采用 Python 3.12+ | 现代语法特性，asyncio 支持完善 |
| 2026-05-20 | 使用 uv 作为包管理 | 速度快，依赖解析优秀 |
| 2026-05-20 | 混合架构设计 | 结合两家框架优势，精简冗余 |
| 2026-05-20 | skill 源文件放 docs/，渐进式多文件披露 | 入口精简，详细内容按需读取；agent 同步副本由 gitignore 排除 |
| 2026-05-20 | 根目录 merco.json 不入库 | 本地开发配置，模板在 config/merco.json.example |
| 2026-05-20 | config 反序列化补全 api_key/base_url | 原 _from_dict 漏字段导致对接非 OpenAI 厂商时 base_url 丢失 |
| 2026-05-20 | 5 处关键集成链路标记为最优先 | 代码已完成但调用链缺失：Sandbox→Tools, Hooks→Agent, Observability→Agent, Memory→Sessions, Scheduler→Runtime |
| 2026-05-31 | Observer report 累计公式用 `acc + (live - last_merged)` | `_merge_to_acc()` 后 acc 含 live 值，直接 acc+live 重复计数；三个容器各司其职：acc 锚点 / live 实时 / last_merged 合并快照 |
| 2026-05-31 | StreamingProvider CancelledError checkpoint 保留为设计 trade-off | async for 内 __anext__ I/O 等待时被取消会丢 partial content，窗口极小且用户主动取消，收益近零，低优先级 |
| 2026-05-31 | LLMClient 统一 None 防护 + extra_params/headers 可配置 | _normalize_tool_calls 归一 tool_call 避免 str += None；extra_params 透传 top_p/seed 等；headers 支持 X-Title 自定义 header；stream_options 收流式 usage |
| 2026-05-31 | _normalize_tool_calls 不假设 tc.function 存在 | scnet 等 API 分 chunk 补全 function（首 chunk 无 function 字段），`func = tc.function; func.name if func else ""` 兼容 |
| 2026-05-31 | 推理泄漏采用日志观察优先策略 | 先加 5 处 WARNING/DEBUG 日志打桩，`--debug` 运行观察；若日志无 WARNING 则判定为 provider 端行为，不改客户端代码 |
