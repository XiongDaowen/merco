# Dashboard render AFTER MCP — fix

`dashboard.render()` 在 `_setup_agent` 里调用，MCP 未加载时已算好文本。

## 改动

`_setup_agent()` 返回 `(agent, dashboard, config_source)` 而非 `(agent, dashboard_text)`。

`run_repl()` 里 MCP 加载之后调 `dashboard.render(agent, config_source=config_source)` 再打印。
