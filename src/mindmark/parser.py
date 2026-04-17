"""Parser for Netscape bookmark HTML files (Chrome/Edge/Firefox export format)."""
from __future__ import annotations

import re
import html as _html
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Bookmark:
    title: str
    url: str
    folder_path: str
    add_date: int
    icon: str | None

    @property
    def domain(self) -> str:
        try:
            return urlparse(self.url).netloc.lower()
        except Exception:
            return ""

    @property
    def path_words(self) -> str:
        try:
            p = urlparse(self.url)
            parts = re.split(r"[/_\-\.=&?%]+", p.path)
            return " ".join(w for w in parts if w and not w.isdigit())
        except Exception:
            return ""

    def embedding_text(self) -> str:
        parts = [self.title]
        if self.folder_path:
            parts.append(f"folder: {self.folder_path}")
        if self.domain:
            parts.append(f"domain: {self.domain}")
        pw = self.path_words
        if pw:
            parts.append(f"path: {pw}")
        return " | ".join(parts)


_TAG = re.compile(r"<(?P<close>/?)(?P<name>[A-Za-z0-9]+)(?P<attrs>[^>]*)>", re.DOTALL)
_ATTR = re.compile(r'(\w+)\s*=\s*"([^"]*)"', re.IGNORECASE)


def _attrs(attr_string: str) -> dict[str, str]:
    return {k.lower(): v for k, v in _ATTR.findall(attr_string)}


def parse_bookmarks(html_text: str) -> list[Bookmark]:
    stack: list[str] = []
    out: list[Bookmark] = []

    pos = 0
    pending_h3 = False
    pending_a: dict[str, str] | None = None

    for m in _TAG.finditer(html_text):
        raw_text = html_text[pos:m.start()]
        pos = m.end()

        name = m.group("name").lower()
        closing = m.group("close") == "/"
        text = _html.unescape(re.sub(r"\s+", " ", raw_text)).strip()

        if pending_h3:
            stack.append(text or "Unnamed")
            pending_h3 = False

        if pending_a is not None:
            title = text or pending_a.get("href", "")
            try:
                add_date = int(pending_a.get("add_date", "0") or "0")
            except ValueError:
                add_date = 0
            out.append(Bookmark(
                title=title,
                url=pending_a["href"],
                folder_path="/".join(stack),
                add_date=add_date,
                icon=pending_a.get("icon"),
            ))
            pending_a = None

        attrs = _attrs(m.group("attrs"))

        if name == "dl" and closing:
            if stack:
                stack.pop()
        elif name == "h3" and not closing:
            pending_h3 = True
        elif name == "a" and not closing and "href" in attrs:
            pending_a = attrs

    if pending_a is not None:
        out.append(Bookmark(
            title=pending_a["href"],
            url=pending_a["href"],
            folder_path="/".join(stack),
            add_date=0,
            icon=pending_a.get("icon"),
        ))

    seen: set[str] = set()
    dedup: list[Bookmark] = []
    for b in out:
        if b.url in seen:
            continue
        seen.add(b.url)
        dedup.append(b)
    return dedup


def parse_file(path: str) -> list[Bookmark]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return parse_bookmarks(f.read())
