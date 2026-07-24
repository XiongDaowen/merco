"""Mercury Code — lightweight AI coding assistant 驱动的自改进软件开发平台"""

import tomllib as _tomllib
from pathlib import Path

_pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"

# 优先从源码 pyproject.toml 读取版本（开发环境），读不到再 fallback
try:
    _text = _pyproject.read_text(encoding="utf-8")
    __version__ = _tomllib.loads(_text)["project"]["version"]
except Exception:
    __version__ = "0.0.0"

__author__ = "Mercury Code Contributors"
