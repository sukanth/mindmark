"""Browser detection, path resolution, and bookmark parsing.

Provides auto-detection of installed browsers and their bookmark files,
with parsers that produce the same ``Bookmark`` dataclass used by the
rest of mindmark.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
import sqlite3

from ..parser import Bookmark
from ..index import SyncResult
from .paths import detect_browsers, BrowserProfile, SUPPORTED_BROWSERS


def parse_browser_bookmarks(profile: BrowserProfile) -> list[Bookmark]:
    """Parse bookmarks from a detected browser profile."""
    if profile.browser_type == "chromium":
        from .chromium import parse_chromium_json
        return parse_chromium_json(profile.bookmark_path)
    elif profile.browser_type == "firefox":
        from .firefox import parse_firefox_places
        return parse_firefox_places(profile.bookmark_path)
    else:
        raise ValueError(f"Unsupported browser type: {profile.browser_type}")


def collect_all_bookmarks(
    browser_filter: str | None = None,
) -> list[tuple[BrowserProfile, list[Bookmark]]]:
    """Detect browsers and parse bookmarks from all (or filtered) profiles.

    Returns a list of (profile, bookmarks) pairs.
    """
    profiles = detect_browsers()
    if browser_filter:
        filt = browser_filter.lower()
        profiles = [p for p in profiles if p.browser_name.lower() == filt]

    results: list[tuple[BrowserProfile, list[Bookmark]]] = []
    for profile in profiles:
        try:
            bookmarks = parse_browser_bookmarks(profile)
            results.append((profile, bookmarks))
        except (OSError, ValueError, KeyError, json.JSONDecodeError,
                sqlite3.Error) as e:
            import sys
            print(
                f"warning: failed to read {profile.browser_name} "
                f"({profile.profile_name}): {e}",
                file=sys.stderr,
            )
    return results
