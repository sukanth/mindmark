from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from mindmark import cli
from mindmark._console import Console
from mindmark.browsers.paths import BrowserProfile


class _FakeIndex:
    search_results = []
    stats_payload = {
        "db_path": "fake.db",
        "model": "test-model",
        "top_domains": [("example.com", 2)],
        "top_folders": [("Work", 1)],
        "total": 2,
    }
    bookmarks = []
    pending = []
    enrichment = {}
    sync_calls = []

    def __init__(self, db_path=None, model_name="test-model"):
        self.db_path = Path(db_path or "fake.db")
        self.model_name = model_name

    def close(self):
        pass

    def search(self, **_kwargs):
        return list(self.search_results)

    def stats(self):
        return dict(self.stats_payload)

    def all_bookmarks(self):
        return list(self.bookmarks)

    def pending_enrichment_urls(self, limit=None):
        return list(self.pending)

    def reset_failed_enrichment(self):
        return 0

    def enrichment_stats(self):
        return dict(self.enrichment)

    def sync(self, bookmarks, source="html"):
        self.sync_calls.append((source, len(bookmarks)))
        return SimpleNamespace(added=len(bookmarks), updated=0, removed=0, unchanged=0)


def _install_fake_index(monkeypatch, fake_index=_FakeIndex):
    monkeypatch.setitem(sys.modules, "mindmark.index", SimpleNamespace(Index=fake_index))


def test_console_color_is_tty_aware_and_can_be_disabled(monkeypatch):
    class TtyBuffer(io.StringIO):
        def isatty(self):
            return True

    out = TtyBuffer()
    Console(color=True, stdout=out).success("Done")
    assert "\033[" in out.getvalue()

    monkeypatch.setenv("NO_COLOR", "1")
    out = TtyBuffer()
    Console(color=True, stdout=out).success("Done")
    assert "\033[" not in out.getvalue()


def test_find_human_output_includes_score_url_folder_excerpt_and_hint(monkeypatch, capsys):
    _FakeIndex.search_results = [
        {
            "score": 0.875,
            "title": "Example",
            "url": "https://example.com/docs",
            "folder_path": "Work/Docs",
            "domain": "example.com",
            "relevant_excerpt": "Helpful excerpt.",
        }
    ]
    _install_fake_index(monkeypatch)

    rc = cli.main(["find", "docs", "--excerpt"])

    assert rc == 0
    captured = capsys.readouterr()
    assert "1. Example" in captured.out
    assert "score=0.875" in captured.out
    assert "folder=Work/Docs" in captured.out
    assert "url=https://example.com/docs" in captured.out
    assert "⤵ Helpful excerpt." in captured.out
    assert "Hint: Open a result with:" in captured.out
    assert captured.err == ""


def test_find_json_preserves_result_list_and_has_no_color(monkeypatch, capsys):
    _FakeIndex.search_results = [
        {
            "score": 0.5,
            "title": "Example",
            "url": "https://example.com",
            "folder_path": "",
            "domain": "example.com",
        }
    ]
    _install_fake_index(monkeypatch)

    rc = cli.main(["find", "example", "--json"])

    assert rc == 0
    captured = capsys.readouterr()
    assert "\033[" not in captured.out
    assert json.loads(captured.out) == _FakeIndex.search_results
    assert captured.err == ""


def test_find_no_results_is_single_actionable_message(monkeypatch, capsys):
    _FakeIndex.search_results = []
    _install_fake_index(monkeypatch)

    rc = cli.main(["find", "missing"])

    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out.count("No matching bookmarks.") == 1
    assert "mindmark sync" in captured.out
    assert captured.err == ""


def test_open_alias_opens_top_result(monkeypatch, capsys):
    opened = []
    _FakeIndex.search_results = [
        {
            "score": 0.9,
            "title": "Open Me",
            "url": "https://open.example.com",
            "folder_path": "",
            "domain": "open.example.com",
        }
    ]
    _install_fake_index(monkeypatch)
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)

    rc = cli.main(["open", "open me"])

    assert rc == 0
    assert opened == ["https://open.example.com"]
    assert "Opened 1. Open Me" in capsys.readouterr().out


def test_stats_json_uses_stable_dictionary(monkeypatch, capsys):
    _install_fake_index(monkeypatch)

    rc = cli.main(["stats", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "db_path": "fake.db",
        "model": "test-model",
        "top_domains": [{"count": 2, "domain": "example.com"}],
        "top_folders": [{"count": 1, "folder": "Work"}],
        "total": 2,
    }


def test_validate_empty_index_json_is_actionable(monkeypatch, capsys):
    _FakeIndex.bookmarks = []
    _install_fake_index(monkeypatch)

    rc = cli.main(["validate", "--json"])

    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 0
    assert "mindmark sync" in payload["message"]


def test_enrich_json_idle(monkeypatch, capsys):
    _FakeIndex.pending = []
    _FakeIndex.enrichment = {"complete": 1}
    _install_fake_index(monkeypatch)
    monkeypatch.setitem(
        sys.modules,
        "mindmark.enricher",
        SimpleNamespace(enrich_pending=lambda *_args, **_kwargs: None),
    )

    rc = cli.main(["enrich", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "idle"
    assert payload["before"] == {"complete": 1}


def test_sync_list_browsers_shows_supported(monkeypatch, capsys):
    import mindmark.browsers.paths as paths

    monkeypatch.setattr(paths, "detect_browsers", lambda: [])

    rc = cli.main(["sync", "--list-browsers"])

    assert rc == 0
    out = capsys.readouterr().out
    for name in ["Chrome", "Edge", "Brave", "Firefox"]:
        assert name in out


def test_sync_browser_filter_json(monkeypatch, capsys):
    import mindmark.browsers as browsers
    import mindmark.browsers.paths as paths

    chrome = BrowserProfile(
        browser_name="Chrome",
        browser_type="chromium",
        profile_name="Default",
        bookmark_path=Path("chrome-bookmarks"),
    )
    firefox = BrowserProfile(
        browser_name="Firefox",
        browser_type="firefox",
        profile_name="default-release",
        bookmark_path=Path("places.sqlite"),
    )
    _FakeIndex.sync_calls = []
    _install_fake_index(monkeypatch)
    monkeypatch.setattr(paths, "detect_browsers", lambda: [chrome, firefox])
    monkeypatch.setattr(browsers, "parse_browser_bookmarks", lambda _profile: [object()])

    rc = cli.main(["sync", "--browser", "Firefox", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert [p["browser"] for p in payload["profiles"]] == ["Firefox"]
    assert payload["summary"]["added"] == 1
    assert _FakeIndex.sync_calls == [("firefox:default-release", 1)]


def test_runtime_errors_are_concise(monkeypatch, capsys):
    class BrokenIndex(_FakeIndex):
        def __init__(self, *args, **kwargs):
            raise RuntimeError("database is locked")

    _install_fake_index(monkeypatch, BrokenIndex)

    rc = cli.main(["stats"])

    assert rc == 1
    captured = capsys.readouterr()
    assert "database is locked" in captured.err
    assert "Traceback" not in captured.err
