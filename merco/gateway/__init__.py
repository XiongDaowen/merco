"""消息网关"""

from .base import GatewayAdapter
from .registry import GatewayRegistry

__all__ = ["GatewayAdapter", "GatewayRegistry"]
