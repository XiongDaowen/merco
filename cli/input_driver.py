"""Terminal input abstraction. Phase 2: PromptToolkitInput. Phase 4: Textual reuse."""

from abc import ABC, abstractmethod


class InputDriver(ABC):
    """Abstract terminal input driver."""

    @abstractmethod
    async def get_input(self, prompt: str) -> str:
        """Get user input line(s). Multiline handled by driver internally."""
        ...
