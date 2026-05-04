"""Tests for the browsers orchestration layer (__init__.py)."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mindmark.browsers import (
    parse_browser_bookmarks,
    collect_all_bookmarks,
)
from mindmark.browsers.paths import BrowserProfile


def _make_chromium_profile(
    tmp_path: Path,
    browser_name: str = "Chrome",
    profile_name: str = "Default",
) -> BrowserProfile:
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
        browser_name=browser_name,
        browser_type="chromium",
        profile_name=profile_name,
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
    with pytest.raises(ValueError, match="Unsupported"):
        parse_browser_bookmarks(profile)


def test_collect_all_bookmarks_with_case_insensitive_filter(tmp_path):
    profiles = []
    for browser, profile_name in [
        ("Chrome", "Default"),
        ("Edge", "Profile 1"),
        ("Brave", "Profile 2"),
    ]:
        browser_dir = tmp_path / browser.lower()
        browser_dir.mkdir()
        profiles.append(_make_chromium_profile(browser_dir, browser, profile_name))

    ff_dir = tmp_path / "firefox"
    ff_dir.mkdir()
    profiles.append(_make_firefox_profile(ff_dir))

    with patch("mindmark.browsers.detect_browsers", return_value=profiles):
        for browser_filter, expected_browser in [
            ("chrome", "Chrome"),
            ("EDGE", "Edge"),
            (" Edge ", "Edge"),
            ("bRaVe", "Brave"),
            ("FIREFOX", "Firefox"),
        ]:
            results = collect_all_bookmarks(browser_filter=browser_filter)
            assert [profile.browser_name for profile, _ in results] == [expected_browser]
            assert results[0][1]

        assert collect_all_bookmarks(browser_filter="safari") == []
        assert collect_all_bookmarks(browser_filter="unknown-browser") == []

        results = collect_all_bookmarks(browser_filter=None)
        assert [profile.browser_name for profile, _ in results] == [
            "Chrome",
            "Edge",
            "Brave",
            "Firefox",
        ]
        whitespace_results = collect_all_bookmarks(browser_filter="  ")
        assert [profile.browser_name for profile, _ in whitespace_results] == [
            "Chrome",
            "Edge",
            "Brave",
            "Firefox",
        ]


def test_collect_all_bookmarks_no_browsers():
    with patch("mindmark.browsers.detect_browsers", return_value=[]):
        results = collect_all_bookmarks()
        assert results == []


def test_collect_all_bookmarks_warns_and_continues_after_parse_error(tmp_path, capsys):
    """A broken profile should print a warning and not block valid profiles."""
    bad_profile = BrowserProfile(
        browser_name="Chrome",
        browser_type="chromium",
        profile_name="Corrupt",
        bookmark_path=tmp_path / "nonexistent",
    )

    good_dir = tmp_path / "good-edge"
    good_dir.mkdir()
    good_profile = _make_chromium_profile(good_dir, "Edge", "Default")

    with patch("mindmark.browsers.detect_browsers", return_value=[bad_profile, good_profile]):
        results = collect_all_bookmarks()
        assert len(results) == 1
        assert results[0][0].browser_name == "Edge"
        assert len(results[0][1]) == 2
        captured = capsys.readouterr()
        assert "warning" in captured.err
        assert "Chrome" in captured.err
        assert "Corrupt" in captured.err
