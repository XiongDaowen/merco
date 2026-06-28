"""Mercury Code — lightweight AI coding assistant 驱动的自改进软件开发平台"""

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("merco")
except PackageNotFoundError:
    # 源码直接运行（未安装）时，从 pyproject.toml 读不到，回退到内置字面量
    __version__ = "0.4.0"

__author__ = "Mercury Code Contributors"
