"""Tests for browser detection and path resolution."""
import sys
from pathlib import Path
from unittest.mock import patch

from mindmark.browsers.paths import detect_browsers, BrowserProfile


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


def test_detect_browsers_returns_list(tmp_path):
    """detect_browsers should return a list (possibly empty) on any platform."""
    # With a fake home, no browsers should be detected
    with patch("mindmark.browsers.paths._home", return_value=tmp_path):
        with patch("mindmark.browsers.paths._local_app_data", return_value=tmp_path / "Local"):
            with patch("mindmark.browsers.paths._app_data", return_value=tmp_path / "Roaming"):
                profiles = detect_browsers()
    assert isinstance(profiles, list)


def test_detect_chromium_with_fake_profile(tmp_path):
    """Simulate a Chrome installation with a Default profile."""
    if sys.platform == "darwin":
        chrome_dir = tmp_path / "Library" / "Application Support" / "Google" / "Chrome"
    elif sys.platform.startswith("linux"):
        chrome_dir = tmp_path / ".config" / "google-chrome"
    else:
        chrome_dir = tmp_path / "Google" / "Chrome" / "User Data"

    default_profile = chrome_dir / "Default"
    default_profile.mkdir(parents=True)
    (default_profile / "Bookmarks").write_text('{"roots":{}}')

    with patch("mindmark.browsers.paths._home", return_value=tmp_path):
        with patch("mindmark.browsers.paths._local_app_data", return_value=tmp_path):
            profiles = detect_browsers()

    chrome_profiles = [p for p in profiles if p.browser_name == "Chrome"]
    assert len(chrome_profiles) >= 1
    assert chrome_profiles[0].profile_name == "Default"
    assert chrome_profiles[0].browser_type == "chromium"


def test_detect_firefox_with_fake_profile(tmp_path):
    """Simulate a Firefox installation with a profile."""
    if sys.platform == "darwin":
        ff_dir = tmp_path / "Library" / "Application Support" / "Firefox" / "Profiles"
    elif sys.platform.startswith("linux"):
        ff_dir = tmp_path / ".mozilla" / "firefox"
    else:
        ff_dir = tmp_path / "Roaming" / "Mozilla" / "Firefox" / "Profiles"

    profile_dir = ff_dir / "abc12345.default-release"
    profile_dir.mkdir(parents=True)
    # Create a minimal places.sqlite
    import sqlite3
    db = profile_dir / "places.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT)")
    con.close()

    with patch("mindmark.browsers.paths._home", return_value=tmp_path):
        with patch("mindmark.browsers.paths._app_data", return_value=tmp_path / "Roaming"):
            profiles = detect_browsers()

    ff_profiles = [p for p in profiles if p.browser_name == "Firefox"]
    assert len(ff_profiles) >= 1
    assert ff_profiles[0].browser_type == "firefox"
    assert "default-release" in ff_profiles[0].profile_name
