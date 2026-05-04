"""Small TTY-aware console formatting helpers."""
from __future__ import annotations

import os
import sys
from typing import TextIO

_TRUTHY = {"1", "true", "yes", "on"}
_COLORS = {
    "muted": "2",
    "status": "36",
    "success": "32",
    "warning": "33",
    "error": "31",
    "accent": "35",
    "bold": "1",
}


def _env_disables_color() -> bool:
    return (
        "NO_COLOR" in os.environ
        or os.environ.get("MINDMARK_NO_COLOR", "").lower() in _TRUTHY
        or os.environ.get("TERM") == "dumb"
    )


class Console:
    def __init__(
        self,
        *,
        color: bool | None = None,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        self.stdout = stdout or sys.stdout
        self.stderr = stderr or sys.stderr
        if color is None:
            self.color = self.stdout.isatty() and not _env_disables_color()
        else:
            self.color = color and not _env_disables_color()

    def style(self, text: str, name: str) -> str:
        code = _COLORS.get(name)
        if not self.color or not code:
            return text
        return f"\033[{code}m{text}\033[0m"

    def out(self, message: str = "", *, style: str | None = None) -> None:
        print(self.style(message, style) if style else message, file=self.stdout)

    def err(self, message: str = "", *, style: str | None = None) -> None:
        print(self.style(message, style) if style else message, file=self.stderr)

    def status(self, message: str) -> None:
        self.out(f"{self.style('→', 'status')} {message}")

    def success(self, message: str) -> None:
        self.out(f"{self.style('✓', 'success')} {message}")

    def warning(self, message: str) -> None:
        self.err(f"{self.style('!', 'warning')} {message}")

    def error(self, message: str) -> None:
        self.err(f"{self.style('✖', 'error')} {message}")

    def hint(self, message: str, *, stderr: bool = False) -> None:
        line = f"{self.style('Hint:', 'accent')} {message}"
        if stderr:
            self.err(line)
        else:
            self.out(line)
