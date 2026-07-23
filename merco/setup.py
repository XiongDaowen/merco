"""交互式 API 配置向导 - merco setup"""

import os
import asyncio
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from merco.core.config import MercoConfig
from merco.core.llm.base import ModelProviderInfo
from merco.core.llm.registry import ModelRegistry
from merco.core.llm.openai_provider import OpenAICompatibleProvider

console = Console()

OUTPUT_PATH = "./merco.json"


def run_setup_wizard() -> None:
    """交互式配置 API provider、key、model，写入 merco.json"""

    # ── 欢迎 ──
    console.print(Panel(
        "[bold]🚀 欢迎使用 Merco！[/bold]\n\n"
        "首次使用需要配置 AI 模型接口。\n"
        "已有 API key？一分钟搞定。\n\n"
        "[dim]按 Ctrl+C 随时退出[/dim]",
        title="Merco Setup",
        border_style="green",
    ))

    # ── 步骤 1：选平台 ──
    provider = _pick_provider(ModelRegistry().list())

    # ── 步骤 2：填 API key ──
    api_key = _ask_api_key(provider)

    # ── 步骤 3：填 model ──
    model = _ask_model(provider)

    # ── 步骤 4：填 base_url ──
    base_url = _ask_base_url(provider)

    # ── 步骤 5：确认 ──
    _confirm_and_save(provider, api_key, model, base_url)


def _pick_provider(providers: list) -> ModelProviderInfo:
    """展示平台列表，让用户选择"""
    console.print("\n[bold]第一步：选择 AI 平台[/bold]\n")

    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("#", width=3, justify="right", style="dim")
    table.add_column("平台", style="bold")
    table.add_column("默认模型", style="dim")
    table.add_column("说明")

    items = list(providers)
    for i, p in enumerate(items, 1):
        table.add_row(str(i), p.display_name, p.default_model, p.description)
    # 自定义选项
    table.add_row(str(len(items) + 1), "[dim]自定义[/dim]", "自行输入", "未收录的平台")

    console.print(table)

    while True:
        try:
            choice = console.input(f"\n[bold yellow]请选择 (1-{len(items) + 1})[/bold yellow]: ").strip()
            idx = int(choice)
            if 1 <= idx <= len(items):
                return items[idx - 1]
            if idx == len(items) + 1:
                return _ask_custom_provider()
            console.print("[red]无效选择，请重新输入[/red]")
        except (ValueError, EOFError, KeyboardInterrupt):
            raise


def _ask_custom_provider() -> ModelProviderInfo:
    """自定义平台：让用户输入必要信息（默认按 OpenAI 兼容协议调用）"""
    console.print("\n[bold]自定义平台[/bold]")
    name = console.input("[dim]平台名称 (如 SCNet)[/dim]: ").strip()
    if not name:
        name = "custom"
    key = name.lower().replace(" ", "-")
    return ModelProviderInfo(
        name=key,
        provider_class=OpenAICompatibleProvider,
        display_name=name,
        description="自定义平台",
    )


def _ask_api_key(provider: ModelProviderInfo) -> str:
    """输入 API key"""
    console.print(f"\n[bold]第二步：配置 {provider.display_name} API Key[/bold]")
    if provider.key_help:
        console.print(f"[dim]获取 Key: {provider.key_help}[/dim]")
    if provider.key_env:
        env_val = os.environ.get(provider.key_env, "")
        if env_val:
            masked = env_val[:8] + "..." if len(env_val) > 8 else env_val
            console.print(f"[dim]环境变量 {provider.key_env} 已设置 ({masked})[/dim]")
            use_env = console.input("[bold yellow]使用环境变量？按 Enter 确认，输入 n 手动填写[/bold yellow]: ").strip().lower()
            if use_env != "n":
                return ""  # 空字符串 = 用环境变量

    while True:
        key = console.input("[bold yellow]API Key[/bold yellow]: ").strip()
        if key:
            return key
        if provider.key_env:
            console.print(f"[dim]留空将使用环境变量 {provider.key_env}[/dim]")
            return ""
        console.print("[red]API Key 不能为空[/red]")


def _ask_model(provider: ModelProviderInfo) -> str:
    """选择或输入模型名"""
    console.print(f"\n[bold]第三步：选择模型[/bold]")

    if provider.models:
        console.print(f"[dim]{provider.display_name} 已知模型:[/dim]")
        for i, m in enumerate(provider.models, 1):
            marker = " ← 推荐" if m == provider.default_model else ""
            console.print(f"  {i}. {m}{marker}")

        console.print(f"  [dim]或直接输入模型名（按 Enter 使用推荐 {provider.default_model}）[/dim]")
        choice = console.input("[bold yellow]模型[/bold yellow]: ").strip()

        if not choice:
            return provider.default_model
        try:
            idx = int(choice)
            if 1 <= idx <= len(provider.models):
                return provider.models[idx - 1]
        except ValueError:
            pass
        return choice  # 用户自定义输入
    else:
        default = provider.default_model or "gpt-4o"
        choice = console.input(
            f"[bold yellow]模型名 (按 Enter 使用 {default})[/bold yellow]: ").strip()
        return choice or default


def _ask_base_url(provider: ModelProviderInfo) -> str:
    """输入或确认 base_url"""
    console.print(f"\n[bold]第四步：API 端点[/bold]")
    if provider.base_url:
        console.print(f"[dim]默认: {provider.base_url}[/dim]")
        choice = console.input("[bold yellow]base_url (按 Enter 使用默认)[/bold yellow]: ").strip()
        return choice or provider.base_url
    else:
        while True:
            choice = console.input("[bold yellow]base_url (必填)[/bold yellow]: ").strip()
            if choice:
                return choice
            console.print("[red]base_url 不能为空[/red]")


def _confirm_and_save(provider: ModelProviderInfo, api_key: str, model: str, base_url: str) -> None:
    """确认配置并写入 merco.json"""
    console.print(f"\n[bold]确认配置[/bold]")
    console.print(f"  平台:     {provider.display_name}")
    console.print(f"  模型:     {model}")
    console.print(f"  API Key:  {'(环境变量)' if not api_key else api_key[:8] + '...' if len(api_key) > 8 else api_key}")
    console.print(f"  base_url: {base_url}")
    console.print(f"  配置文件: {OUTPUT_PATH}")

    confirm = console.input("\n[bold yellow]确认并保存？按 Enter 确认，输入 n 取消[/bold yellow]: ").strip().lower()
    if confirm == "n":
        console.print("[dim]已取消，配置未保存[/dim]")
        return

    # 加载已有配置（如果存在），只更新 model 部分
    if Path(OUTPUT_PATH).exists():
        cfg = MercoConfig.load(OUTPUT_PATH)
    else:
        cfg = MercoConfig()

    cfg.model.provider = provider.name
    cfg.model.model = model
    cfg.model.base_url = base_url
    if api_key:
        cfg.model.api_key = api_key

    cfg.save(OUTPUT_PATH)
    console.print(f"\n[green]✅ 配置已保存到 {OUTPUT_PATH}[/green]")

    # ── 安装内置技能 ──
    from merco.skills.builtin import install_builtin_skills
    installed = install_builtin_skills()
    if installed:
        console.print(f"[green]✅ 已安装内置技能: {', '.join(installed)}[/green]")

    console.print("[dim]运行 merco 开始使用[/dim]")
