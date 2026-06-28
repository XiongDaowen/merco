"""Recovery strategies."""
from .wait import WaitRecovery
from .model_fallback import ModelFallbackRecovery

__all__ = ["WaitRecovery", "ModelFallbackRecovery"]
