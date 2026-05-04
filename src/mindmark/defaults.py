"""Lightweight shared defaults for CLI and index modules."""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def default_db_path(create: bool = True) -> Path:
    env = os.environ.get("MINDMARK_HOME")
    if env:
        base = Path(env)
    elif os.name == "nt":
        local = os.environ.get("LOCALAPPDATA")
        base = Path(local) / "mindmark" if local else Path.home() / ".mindmark"
    else:
        base = Path.home() / ".mindmark"
    if create:
        base.mkdir(parents=True, exist_ok=True)
    return base / "index.db"
