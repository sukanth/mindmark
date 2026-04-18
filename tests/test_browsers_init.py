"""Tests for the browsers orchestration layer (__init__.py)."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from mindmark.browsers import (
    parse_browser_bookmarks,
    collect_all_bookmarks,
)
from mindmark.browsers.paths import BrowserProfile


def _make_chromium_profile(tmp_path: Path) -> BrowserProfile:
    """Create a fake Chromium profile with a Bookmarks JSON file."""
    bookmark_file = tmp_path / "Bookmarks"
    data = {
        "roots": {
            "bookmark_bar": {
                "children": [
                    {"name": "Example", "type": "url", "url": "https://example.com"},
                    {"name": "Test", "type": "url", "url": "https://test.com"},
                ],
                "name": "Bookmarks Bar",
                "type": "folder",
            },
            "other": {"children": [], "name": "Other", "type": "folder"},
            "synced": {"children": [], "name": "Synced", "type": "folder"},
        }
    }
    bookmark_file.write_text(json.dumps(data))
    return BrowserProfile(
        browser_name="Chrome",
        browser_type="chromium",
        profile_name="Default",
        bookmark_path=bookmark_file,
    )


def _make_firefox_profile(tmp_path: Path) -> BrowserProfile:
    """Create a fake Firefox profile with a places.sqlite file."""
    import sqlite3

    db_path = tmp_path / "places.sqlite"
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT);
        CREATE TABLE moz_bookmarks (
            id INTEGER PRIMARY KEY, type INTEGER, fk INTEGER,
            parent INTEGER, title TEXT, dateAdded INTEGER
        );
        INSERT INTO moz_bookmarks (id, type, fk, parent, title) VALUES
            (1, 2, NULL, 0, 'root'), (2, 2, NULL, 1, 'menu');
        INSERT INTO moz_places (id, url) VALUES (1, 'https://firefox.example.com');
        INSERT INTO moz_bookmarks (id, type, fk, parent, title, dateAdded) VALUES
            (100, 1, 1, 2, 'Firefox Example', 0);
    """)
    con.close()
    return BrowserProfile(
        browser_name="Firefox",
        browser_type="firefox",
        profile_name="default-release",
        bookmark_path=db_path,
    )


def test_parse_browser_bookmarks_chromium(tmp_path):
    profile = _make_chromium_profile(tmp_path)
    bookmarks = parse_browser_bookmarks(profile)
    assert len(bookmarks) == 2
    urls = {b.url for b in bookmarks}
    assert "https://example.com" in urls
    assert "https://test.com" in urls


def test_parse_browser_bookmarks_firefox(tmp_path):
    profile = _make_firefox_profile(tmp_path)
    bookmarks = parse_browser_bookmarks(profile)
    assert len(bookmarks) == 1
    assert bookmarks[0].url == "https://firefox.example.com"


def test_parse_browser_bookmarks_unsupported():
    profile = BrowserProfile(
        browser_name="Safari",
        browser_type="safari",
        profile_name="Default",
        bookmark_path=Path("/fake"),
    )
    try:
        parse_browser_bookmarks(profile)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unsupported" in str(e)


def test_collect_all_bookmarks_with_filter(tmp_path):
    chrome_dir = tmp_path / "chrome"
    chrome_dir.mkdir()
    chrome_profile = _make_chromium_profile(chrome_dir)

    ff_dir = tmp_path / "firefox"
    ff_dir.mkdir()
    ff_profile = _make_firefox_profile(ff_dir)

    fake_profiles = [chrome_profile, ff_profile]

    with patch("mindmark.browsers.detect_browsers", return_value=fake_profiles):
        # Filter to Chrome only
        results = collect_all_bookmarks(browser_filter="Chrome")
        assert len(results) == 1
        assert results[0][0].browser_name == "Chrome"

        # Filter to Firefox only
        results = collect_all_bookmarks(browser_filter="firefox")
        assert len(results) == 1
        assert results[0][0].browser_name == "Firefox"

        # No filter — gets all
        results = collect_all_bookmarks(browser_filter=None)
        assert len(results) == 2


def test_collect_all_bookmarks_no_browsers():
    with patch("mindmark.browsers.detect_browsers", return_value=[]):
        results = collect_all_bookmarks()
        assert results == []


def test_collect_all_bookmarks_handles_parse_error(tmp_path, capsys):
    """A broken profile should print a warning and not crash."""
    bad_profile = BrowserProfile(
        browser_name="Chrome",
        browser_type="chromium",
        profile_name="Corrupt",
        bookmark_path=tmp_path / "nonexistent",
    )
    with patch("mindmark.browsers.detect_browsers", return_value=[bad_profile]):
        results = collect_all_bookmarks()
        assert results == []
        captured = capsys.readouterr()
        assert "warning" in captured.err
        assert "Chrome" in captured.err
