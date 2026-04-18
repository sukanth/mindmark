"""OS-specific browser bookmark path resolution and detection."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrowserProfile:
    """A detected browser profile with its bookmark file path."""
    browser_name: str          # e.g. "Chrome", "Firefox"
    browser_type: str          # "chromium" or "firefox"
    profile_name: str          # e.g. "Default", "Profile 1", "default-release"
    bookmark_path: Path        # full path to the bookmark file
    source_id: str = ""        # unique id like "chrome:Default"

    def __post_init__(self):
        if not self.source_id:
            sid = f"{self.browser_name.lower()}:{self.profile_name}"
            object.__setattr__(self, "source_id", sid)


# ---------------------------------------------------------------------------
# Browser path definitions per OS
# ---------------------------------------------------------------------------

def _home() -> Path:
    return Path.home()


def _local_app_data() -> Path:
    """Windows %LOCALAPPDATA%."""
    val = os.environ.get("LOCALAPPDATA")
    return Path(val) if val else Path.home() / "AppData" / "Local"


def _app_data() -> Path:
    """Windows %APPDATA%."""
    val = os.environ.get("APPDATA")
    return Path(val) if val else Path.home() / "AppData" / "Roaming"


# Each entry: (browser_name, browser_type, path_parts_tuple)
# Path parts are joined with Path.joinpath() — no OS-specific separators.
_CHROMIUM_BOOKMARK_FILE = "Bookmarks"

_BROWSER_DEFS: dict[str, list[tuple[str, str, tuple[str, ...]]]] = {
    "darwin": [
        ("Chrome", "chromium",
         ("Library", "Application Support", "Google", "Chrome")),
        ("Edge", "chromium",
         ("Library", "Application Support", "Microsoft Edge")),
        ("Brave", "chromium",
         ("Library", "Application Support", "BraveSoftware", "Brave-Browser")),
        ("Firefox", "firefox",
         ("Library", "Application Support", "Firefox", "Profiles")),
    ],
    "linux": [
        ("Chrome", "chromium", (".config", "google-chrome")),
        ("Edge", "chromium", (".config", "microsoft-edge")),
        ("Brave", "chromium", (".config", "BraveSoftware", "Brave-Browser")),
        ("Firefox", "firefox", (".mozilla", "firefox")),
    ],
    "win32": [
        ("Chrome", "chromium", ("Google", "Chrome", "User Data")),
        ("Edge", "chromium", ("Microsoft", "Edge", "User Data")),
        ("Brave", "chromium", ("BraveSoftware", "Brave-Browser", "User Data")),
        ("Firefox", "firefox", ()),  # handled specially
    ],
}


SUPPORTED_BROWSERS = ["chrome", "edge", "brave", "firefox"]


def _chromium_base(path_parts: tuple[str, ...]) -> Path | None:
    """Resolve the Chromium base directory for the current OS."""
    if sys.platform == "win32":
        base = _local_app_data().joinpath(*path_parts)
    else:
        base = _home().joinpath(*path_parts)
    return base if base.is_dir() else None


def _firefox_base(path_parts: tuple[str, ...]) -> Path | None:
    """Resolve the Firefox profiles directory for the current OS."""
    if sys.platform == "win32":
        base = _app_data() / "Mozilla" / "Firefox" / "Profiles"
    else:
        base = _home().joinpath(*path_parts) if path_parts else None
    return base if base and base.is_dir() else None


def _discover_chromium_profiles(base: Path) -> list[BrowserProfile]:
    """Find all Chromium profiles in a browser's data directory."""
    profiles: list[BrowserProfile] = []
    # Chromium profile dirs: "Default", "Profile 1", "Profile 2", etc.
    candidates = sorted(base.iterdir()) if base.is_dir() else []
    for d in candidates:
        if not d.is_dir():
            continue
        bookmark_file = d / _CHROMIUM_BOOKMARK_FILE
        if bookmark_file.is_file():
            profiles.append(BrowserProfile(
                browser_name="",  # filled by caller
                browser_type="chromium",
                profile_name=d.name,
                bookmark_path=bookmark_file,
            ))
    return profiles


def _discover_firefox_profiles(base: Path) -> list[BrowserProfile]:
    """Find all Firefox profiles in the profiles directory."""
    profiles: list[BrowserProfile] = []
    if not base.is_dir():
        return profiles
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        places = d / "places.sqlite"
        if places.is_file():
            profiles.append(BrowserProfile(
                browser_name="Firefox",
                browser_type="firefox",
                profile_name=d.name,
                bookmark_path=places,
            ))
    return profiles


def detect_browsers() -> list[BrowserProfile]:
    """Auto-detect installed browsers and their profiles.

    Returns a list of ``BrowserProfile`` instances for every discovered
    profile that contains a bookmark file.
    """
    platform = sys.platform
    if platform.startswith("linux"):
        platform = "linux"

    defs = _BROWSER_DEFS.get(platform, [])
    found: list[BrowserProfile] = []

    for browser_name, browser_type, path_parts in defs:
        if browser_type == "chromium":
            base = _chromium_base(path_parts)
            if base is None:
                continue
            for p in _discover_chromium_profiles(base):
                found.append(BrowserProfile(
                    browser_name=browser_name,
                    browser_type=p.browser_type,
                    profile_name=p.profile_name,
                    bookmark_path=p.bookmark_path,
                ))
        elif browser_type == "firefox":
            base = _firefox_base(path_parts)
            if base is None:
                continue
            found.extend(_discover_firefox_profiles(base))

    return found
