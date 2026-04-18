"""Tests for the Chromium JSON bookmark parser."""
import json
import tempfile
from pathlib import Path

from mindmark.browsers.chromium import parse_chromium_json


SAMPLE_CHROMIUM = {
    "checksum": "abc123",
    "roots": {
        "bookmark_bar": {
            "children": [
                {
                    "date_added": "13300000000000000",
                    "name": "Python Docs",
                    "type": "url",
                    "url": "https://docs.python.org/3/",
                },
                {
                    "children": [
                        {
                            "date_added": "13300000000000001",
                            "name": "GitHub",
                            "type": "url",
                            "url": "https://github.com",
                        },
                        {
                            "children": [
                                {
                                    "date_added": "13300000000000002",
                                    "name": "Kusto Guide",
                                    "type": "url",
                                    "url": "https://eng.ms/docs/kusto",
                                }
                            ],
                            "name": "Internal",
                            "type": "folder",
                        },
                    ],
                    "name": "Work",
                    "type": "folder",
                },
            ],
            "name": "Bookmarks Bar",
            "type": "folder",
        },
        "other": {
            "children": [
                {
                    "name": "Stack Overflow",
                    "type": "url",
                    "url": "https://stackoverflow.com",
                }
            ],
            "name": "Other bookmarks",
            "type": "folder",
        },
        "synced": {
            "children": [],
            "name": "Mobile bookmarks",
            "type": "folder",
        },
    },
    "version": 1,
}


def _write_json(data: dict) -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(data, f)
    f.close()
    return Path(f.name)


def test_parses_urls_and_titles():
    path = _write_json(SAMPLE_CHROMIUM)
    bms = parse_chromium_json(path)
    by_url = {b.url: b for b in bms}
    assert "https://docs.python.org/3/" in by_url
    assert by_url["https://docs.python.org/3/"].title == "Python Docs"
    assert "https://github.com" in by_url
    assert "https://stackoverflow.com" in by_url
    path.unlink()


def test_folder_paths():
    path = _write_json(SAMPLE_CHROMIUM)
    bms = parse_chromium_json(path)
    by_url = {b.url: b for b in bms}
    # Top-level bar bookmark
    assert by_url["https://docs.python.org/3/"].folder_path == "Bookmarks Bar"
    # Nested in Work
    assert by_url["https://github.com"].folder_path == "Bookmarks Bar/Work"
    # Nested in Work/Internal
    assert by_url["https://eng.ms/docs/kusto"].folder_path == "Bookmarks Bar/Work/Internal"
    # "Other" root
    assert by_url["https://stackoverflow.com"].folder_path == "Other bookmarks"
    path.unlink()


def test_deduplicates_by_url():
    data = json.loads(json.dumps(SAMPLE_CHROMIUM))
    # Add a duplicate URL in "other"
    data["roots"]["other"]["children"].append({
        "name": "Python Docs Dup",
        "type": "url",
        "url": "https://docs.python.org/3/",
    })
    path = _write_json(data)
    bms = parse_chromium_json(path)
    python_urls = [b for b in bms if b.url == "https://docs.python.org/3/"]
    assert len(python_urls) == 1
    path.unlink()


def test_empty_roots():
    data = {"roots": {"bookmark_bar": {"children": [], "name": "Bar", "type": "folder"}}}
    path = _write_json(data)
    bms = parse_chromium_json(path)
    assert bms == []
    path.unlink()


def test_embedding_text_contains_key_fields():
    path = _write_json(SAMPLE_CHROMIUM)
    bms = parse_chromium_json(path)
    k = next(b for b in bms if "kusto" in b.url)
    t = k.embedding_text()
    assert "Kusto Guide" in t
    assert "eng.ms" in t
    assert "Work/Internal" in t
    path.unlink()
