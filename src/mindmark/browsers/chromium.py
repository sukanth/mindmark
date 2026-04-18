"""Parse Chromium-based browser bookmarks (Chrome, Edge, Brave).

The ``Bookmarks`` file is JSON with this structure::

    {
      "roots": {
        "bookmark_bar": { "children": [...] },
        "other":        { "children": [...] },
        "synced":       { "children": [...] }
      }
    }

Each node is either a **folder** (``"type": "folder"``, has ``children``)
or a **url** (``"type": "url"``, has ``url`` + ``name``).
"""
from __future__ import annotations

import json
from pathlib import Path

from ..parser import Bookmark


def parse_chromium_json(path: Path) -> list[Bookmark]:
    """Parse a Chromium ``Bookmarks`` JSON file into a list of Bookmark objects.

    Deduplicates by URL (keeps the first occurrence).
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    roots = data.get("roots", {})
    bookmarks: list[Bookmark] = []
    seen: set[str] = set()

    for root_name in ("bookmark_bar", "other", "synced"):
        node = roots.get(root_name)
        if node and isinstance(node, dict):
            _walk(node, [], bookmarks, seen)

    return bookmarks


def _walk(
    node: dict,
    folder_stack: list[str],
    out: list[Bookmark],
    seen: set[str],
) -> None:
    """Recursively walk a Chromium bookmark tree node."""
    node_type = node.get("type", "")

    if node_type == "url":
        url = node.get("url", "")
        if not url or url in seen:
            return
        seen.add(url)

        name = node.get("name", url)
        try:
            add_date_str = node.get("date_added", "0")
            # Chromium stores dates as microseconds since 1601-01-01
            add_date = int(add_date_str) if add_date_str else 0
        except (ValueError, TypeError):
            add_date = 0

        out.append(Bookmark(
            title=name,
            url=url,
            folder_path="/".join(folder_stack),
            add_date=add_date,
            icon=None,
        ))

    elif node_type == "folder":
        folder_name = node.get("name", "Unnamed")
        children = node.get("children", [])
        for child in children:
            _walk(child, folder_stack + [folder_name], out, seen)
