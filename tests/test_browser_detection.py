"""Tests for browser detection and path resolution."""
import sys
from pathlib import Path

import pytest

from mindmark.browsers.paths import BrowserProfile, detect_browsers


SUPPORTED_PLATFORMS = ("win32", "darwin", "linux")
PROFILE_NAMES = {
    "Chrome": "Default",
    "Edge": "Profile 1",
    "Brave": "Profile 2",
    "Firefox": "abc12345.default-release",
}


def _configure_platform(monkeypatch, tmp_path: Path, platform: str) -> dict[str, Path]:
    roots = {
        "home": tmp_path / "home",
        "local": tmp_path / "local",
        "roaming": tmp_path / "roaming",
    }
    for root in roots.values():
        root.mkdir()

    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(Path, "home", lambda: roots["home"])
    monkeypatch.setenv("LOCALAPPDATA", str(roots["local"]))
    monkeypatch.setenv("APPDATA", str(roots["roaming"]))
    return roots


def _browser_base(roots: dict[str, Path], platform: str, browser: str) -> Path:
    paths = {
        "win32": {
            "Chrome": roots["local"] / "Google" / "Chrome" / "User Data",
            "Edge": roots["local"] / "Microsoft" / "Edge" / "User Data",
            "Brave": roots["local"] / "BraveSoftware" / "Brave-Browser" / "User Data",
            "Firefox": roots["roaming"] / "Mozilla" / "Firefox" / "Profiles",
        },
        "darwin": {
            "Chrome": roots["home"] / "Library" / "Application Support" / "Google" / "Chrome",
            "Edge": roots["home"] / "Library" / "Application Support" / "Microsoft Edge",
            "Brave": (
                roots["home"]
                / "Library"
                / "Application Support"
                / "BraveSoftware"
                / "Brave-Browser"
            ),
            "Firefox": roots["home"] / "Library" / "Application Support" / "Firefox" / "Profiles",
        },
        "linux": {
            "Chrome": roots["home"] / ".config" / "google-chrome",
            "Edge": roots["home"] / ".config" / "microsoft-edge",
            "Brave": roots["home"] / ".config" / "BraveSoftware" / "Brave-Browser",
            "Firefox": roots["home"] / ".mozilla" / "firefox",
        },
    }
    return paths[platform][browser]


def _create_fake_profile(base: Path, browser: str) -> tuple[str, str, Path]:
    browser_type = "firefox" if browser == "Firefox" else "chromium"
    profile_name = PROFILE_NAMES[browser]
    profile_dir = base / profile_name
    profile_dir.mkdir(parents=True)
    bookmark_path = profile_dir / ("places.sqlite" if browser_type == "firefox" else "Bookmarks")
    bookmark_path.write_text("fake bookmark storage")
    return profile_name, browser_type, bookmark_path


def test_browser_profile_source_id():
    p = BrowserProfile(
        browser_name="Chrome",
        browser_type="chromium",
        profile_name="Default",
        bookmark_path=Path("/fake/path"),
    )
    assert p.source_id == "chrome:Default"


def test_browser_profile_custom_source_id():
    p = BrowserProfile(
        browser_name="Chrome",
        browser_type="chromium",
        profile_name="Default",
        bookmark_path=Path("/fake/path"),
        source_id="custom:id",
    )
    assert p.source_id == "custom:id"


@pytest.mark.parametrize("platform", SUPPORTED_PLATFORMS)
def test_detect_browsers_returns_empty_list_without_profiles(tmp_path, monkeypatch, platform):
    """detect_browsers should return a list (possibly empty) on any platform."""
    _configure_platform(monkeypatch, tmp_path, platform)

    profiles = detect_browsers()

    assert profiles == []


@pytest.mark.parametrize("platform", SUPPORTED_PLATFORMS)
def test_detect_supported_browser_profiles_by_platform(tmp_path, monkeypatch, platform):
    """Simulate all supported browsers on every supported platform."""
    roots = _configure_platform(monkeypatch, tmp_path, platform)
    expected = {}
    for browser in PROFILE_NAMES:
        profile_name, browser_type, bookmark_path = _create_fake_profile(
            _browser_base(roots, platform, browser),
            browser,
        )
        expected[(browser, profile_name)] = (browser_type, bookmark_path)

    profiles = detect_browsers()

    detected = {(p.browser_name, p.profile_name): p for p in profiles}
    assert set(detected) == set(expected)
    for key, (browser_type, bookmark_path) in expected.items():
        profile = detected[key]
        assert profile.browser_type == browser_type
        assert profile.bookmark_path == bookmark_path
        assert profile.source_id == f"{key[0].lower()}:{key[1]}"
