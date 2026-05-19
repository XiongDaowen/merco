# 关键决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-20 | 采用 Python 3.12+ | 现代语法特性，asyncio 支持完善 |
| 2026-05-20 | 使用 uv 作为包管理 | 速度快，依赖解析优秀 |
| 2026-05-20 | 混合架构设计 | 结合两家框架优势，精简冗余 |
| 2026-05-20 | skill 源文件放 docs/，渐进式多文件披露 | 入口精简，详细内容按需读取；agent 同步副本由 gitignore 排除 |
| 2026-05-20 | 根目录 openmercury.json 不入库 | 本地开发配置，模板在 config/openmercury.json.example |
| 2026-05-20 | config 反序列化补全 api_key/base_url | 原 _from_dict 漏字段导致对接非 OpenAI 厂商时 base_url 丢失 |
| 2026-05-20 | 5 处关键集成链路标记为最优先 | 代码已完成但调用链缺失：Sandbox→Tools, Hooks→Agent, Observability→Agent, Memory→Sessions, Scheduler→Runtime |
