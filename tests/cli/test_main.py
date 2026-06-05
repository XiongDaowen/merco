"""cli/main.py 单元测试 — 进度条 _fmt 占位逻辑

修复目标：启动后到第 1 次 API 响应前，_fmt(0, is_estimate=True) 返回 "—"
而不是猜数字（例如 17K 估算值偏大）。
"""

from cli.main import _fmt


def test_fmt_returns_dash_when_is_estimate():
    """修复核心：is_estimate=True 一律占位 "—"，不管 n 是 0 还是估算值（如 12K）。

    启动后到第 1 次 API 响应前，n 实际是估算值（~12K），不是 0。
    占位条件只看 is_estimate，不看 n，避免用户看到偏大估算误判。
    """
    assert _fmt(0, is_estimate=True) == "—"
    # 关键：估算值（如 12000）也必须占位
    assert _fmt(12000, is_estimate=True) == "—"
    # 任意非零估算值都占位
    assert _fmt(500, is_estimate=True) == "—"


def test_fmt_returns_zero_string_when_actual_zero():
    """is_estimate=False 时 n=0 仍返回 "0"，与历史行为一致。"""
    assert _fmt(0) == "0"


def test_fmt_returns_dash_default_compat():
    """不传 is_estimate（默认 False）时 n=0 返回 "0"，保持向后兼容。"""
    # 默认参数必须 is_estimate=False，否则会误把真实 0 token 也显示成占位
    assert _fmt(0) == "0"
    # 显式 is_estimate=False 同义
    assert _fmt(0, is_estimate=False) == "0"


def test_fmt_normal_case_still_works():
    """正常数值格式化路径未受影响：n<1000 直接返回，n>=1000 转 K。"""
    assert _fmt(500) == "500"
    # 6700 bytes / 1024 = 6.54K → "6.5K"
    assert _fmt(6700) == "6.5K"
    assert _fmt(17000) == "16.6K"
    # 实测时 12000 → 11.7K
    assert _fmt(12000) == "11.7K"
    # is_estimate=False 时正常 K 格式化（不被占位）
    assert _fmt(12000, is_estimate=False) == "11.7K"
