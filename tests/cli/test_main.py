"""cli/main.py 单元测试 — 进度条 _fmt 占位逻辑

修复目标：启动后到第 1 次 API 响应前，_fmt(0, is_estimate=True) 返回 "—"
而不是猜数字（例如 17K 估算值偏大）。
"""

from cli.main import _fmt


def test_fmt_returns_dash_when_is_estimate_and_zero():
    """修复核心：is_estimate=True 且 n=0 时返回占位 "—"，不显示估算值。"""
    assert _fmt(0, is_estimate=True) == "—"


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
    # is_estimate 对非零值无效（不应让 6700 也变 "—"）
    assert _fmt(6700, is_estimate=True) == "6.5K"
