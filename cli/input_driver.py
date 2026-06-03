"""Terminal input abstraction. Phase 2: PromptToolkitInput. Phase 4: Textual reuse."""

from abc import ABC, abstractmethod


class InputDriver(ABC):
    """Abstract terminal input driver."""

    @abstractmethod
    async def get_input(self, prompt: str) -> str:
        """Get user input line(s). Multiline handled by driver internally."""
        ...


import os
import time
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.styles import Style

_PASTE_THRESHOLD = 500  # chars threshold for paste archive


class InputInterrupt(Exception):
    """Raised by PromptToolkitInput when Ctrl+C pressed with empty buffer."""


class PromptToolkitInput(InputDriver):
    """prompt_toolkit: paste protection, multiline, command completion, history."""

    def __init__(self, commands: list[str] | None = None):
        hist_path = os.path.expanduser("~/.merco/input_history")
        os.makedirs(os.path.dirname(hist_path), exist_ok=True)

        completer = WordCompleter(commands or [], sentence=True)

        bindings = KeyBindings()

        @bindings.add(Keys.Escape, Keys.Enter)
        def _(event):
            """Alt+Enter: insert newline for multiline input"""
            event.current_buffer.insert_text("\n")

        @bindings.add(Keys.ControlC)
        def _(event):
            """Ctrl+C: clear text if present, signal interrupt if empty"""
            buff = event.current_buffer
            if buff.text:
                buff.text = ""
            else:
                event.app.exit(exception=InputInterrupt())

        self._session = PromptSession(
            history=FileHistory(hist_path),
            completer=completer,
            key_bindings=bindings,
            reserve_space_for_menu=4,
            style=Style.from_dict({
                "prompt": "bold",
                "completion-menu.completion": "bg:#444 #fff",
            }),
        )

        # Paste control: stash long pastes and display short marker
        self._paste_stash: str | None = None

        def _on_text_changed(buf: Buffer):
            if len(buf.text) >= _PASTE_THRESHOLD and not buf.text.startswith("[已粘贴"):
                self._paste_stash = buf.text
                buf.text = f"[已粘贴 {len(buf.text)} 字]"

        self._session.default_buffer.on_text_changed += _on_text_changed

    async def get_input(self, prompt: str) -> str:
        try:
            # handle_sigint=False: 不覆盖我们的 SIGINT 信号处理器
            text = await self._session.prompt_async(prompt, handle_sigint=False)
        except InputInterrupt:
            raise  # propagate to REPL for exit handling

        # Swap paste marker back to original text before returning
        if self._paste_stash and text.startswith("[已粘贴"):
            text = self._paste_stash
            self._paste_stash = None

        # Archive long input to file (human reference)
        if len(text) >= _PASTE_THRESHOLD:
            self._save_paste(text)

        return text

    def _save_paste(self, text: str) -> None:
        tmpdir = os.path.expanduser("~/.merco/pastes")
        os.makedirs(tmpdir, exist_ok=True)
        ts = int(time.time() * 1000)
        path = os.path.join(tmpdir, f"{ts}.txt")
        Path(path).write_text(text, encoding="utf-8")

    def update_commands(self, commands: list[str]) -> None:
        """Dynamically update completion word list."""
        self._session.completer = WordCompleter(commands, sentence=True)
