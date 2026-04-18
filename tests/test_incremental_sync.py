"""Tests for incremental sync logic in Index."""
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import numpy as np

from mindmark.parser import Bookmark
from mindmark.index import Index, SyncResult, _content_hash


def _make_bookmark(url: str, title: str = "T", folder: str = "") -> Bookmark:
    return Bookmark(title=title, url=url, folder_path=folder, add_date=0, icon=None)


def _make_index(db_path: Path) -> Index:
    """Create an Index with a mock embedder to avoid loading the real model."""
    idx = Index(db_path=db_path)
    mock_embedder = MagicMock()
    dim = 4
    def fake_embed(texts):
        vecs = np.random.RandomState(42).randn(len(texts), dim).astype(np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms
    mock_embedder.embed.side_effect = fake_embed
    mock_embedder.embed_one.side_effect = lambda t: fake_embed([t])[0]
    idx.embedder = mock_embedder
    return idx


@pytest.fixture
def idx(tmp_path):
    """Yield an Index with a mock embedder; close DB on teardown."""
    index = _make_index(tmp_path / "test.db")
    yield index
    index.close()


def test_sync_adds_new_bookmarks(idx):
    bms = [
        _make_bookmark("https://a.com", "A"),
        _make_bookmark("https://b.com", "B"),
    ]
    result = idx.sync(bms, source="chrome:Default")
    assert result.added == 2
    assert result.updated == 0
    assert result.removed == 0
    assert result.unchanged == 0
    assert not idx.is_empty()


def test_sync_unchanged_skips_embedding(idx):
    bms = [_make_bookmark("https://a.com", "A")]
    idx.sync(bms, source="test")

    # Reset call count
    idx.embedder.embed.reset_mock()

    # Sync again with same data
    result = idx.sync(bms, source="test")
    assert result.added == 0
    assert result.unchanged == 1
    # embed should NOT be called for unchanged bookmarks
    idx.embedder.embed.assert_not_called()


def test_sync_updates_changed_bookmarks(idx):
    bms = [_make_bookmark("https://a.com", "A", "Folder1")]
    idx.sync(bms, source="test")

    # Change the title
    bms2 = [_make_bookmark("https://a.com", "A Updated", "Folder1")]
    result = idx.sync(bms2, source="test")
    assert result.updated == 1
    assert result.added == 0
    assert result.unchanged == 0

    # Verify the title was updated in the DB
    cur = idx.con.cursor()
    cur.execute("SELECT title FROM bookmarks WHERE url = ?", ("https://a.com",))
    assert cur.fetchone()[0] == "A Updated"


def test_sync_removes_deleted_bookmarks(idx):
    bms = [
        _make_bookmark("https://a.com", "A"),
        _make_bookmark("https://b.com", "B"),
    ]
    idx.sync(bms, source="test")

    # Remove one bookmark
    bms2 = [_make_bookmark("https://a.com", "A")]
    result = idx.sync(bms2, source="test")
    assert result.removed == 1
    assert result.unchanged == 1

    # Verify b.com is gone
    cur = idx.con.cursor()
    cur.execute("SELECT COUNT(*) FROM bookmarks WHERE url = ?", ("https://b.com",))
    assert cur.fetchone()[0] == 0


def test_multi_source_no_cross_deletion(idx):
    """Syncing source A should not delete bookmarks from source B."""
    # Source A adds url X
    bms_a = [_make_bookmark("https://shared.com", "Shared")]
    idx.sync(bms_a, source="chrome:Default")

    # Source B also adds url X
    bms_b = [_make_bookmark("https://shared.com", "Shared")]
    idx.sync(bms_b, source="firefox:default")

    # Source A removes url X
    result = idx.sync([], source="chrome:Default")
    assert result.removed == 1  # removed from source A

    # But the bookmark should still exist (source B still references it)
    cur = idx.con.cursor()
    cur.execute("SELECT COUNT(*) FROM bookmarks WHERE url = ?", ("https://shared.com",))
    assert cur.fetchone()[0] == 1

    # Now remove from source B too
    result = idx.sync([], source="firefox:default")
    cur.execute("SELECT COUNT(*) FROM bookmarks WHERE url = ?", ("https://shared.com",))
    assert cur.fetchone()[0] == 0  # now truly gone


def test_sync_result_str():
    r = SyncResult(added=3, updated=1, removed=2, unchanged=10)
    s = str(r)
    assert "3 new" in s
    assert "1 updated" in s
    assert "2 removed" in s


def test_content_hash_deterministic():
    b = _make_bookmark("https://a.com", "A", "Work")
    h1 = _content_hash(b)
    h2 = _content_hash(b)
    assert h1 == h2
    assert len(h1) == 16  # truncated sha256


def test_content_hash_changes_on_title_change():
    b1 = _make_bookmark("https://a.com", "A", "Work")
    b2 = _make_bookmark("https://a.com", "B", "Work")
    assert _content_hash(b1) != _content_hash(b2)


def test_schema_migration_on_old_db(tmp_path):
    """Ensure opening a v1 database migrates cleanly."""
    db_path = tmp_path / "old.db"
    # Create a v1 database (no content_hash, no bookmark_sources)
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            folder_path TEXT NOT NULL,
            domain TEXT NOT NULL,
            add_date INTEGER NOT NULL,
            icon TEXT,
            embedding BLOB NOT NULL,
            dim INTEGER NOT NULL
        );
    """)
    con.close()

    # Opening with Index should trigger migration
    idx = Index(db_path=db_path)
    try:
        cur = idx.con.cursor()
        cols = {r[1] for r in cur.execute("PRAGMA table_info(bookmarks)")}
        assert "content_hash" in cols

        tables = {r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert "bookmark_sources" in tables
    finally:
        idx.close()


# ---- rebuild() tests ----

def test_rebuild_populates_content_hash(idx):
    """rebuild() must set content_hash so sync() can do incremental diffs."""
    bms = [_make_bookmark("https://a.com", "A", "Work")]
    idx.rebuild(bms)

    cur = idx.con.cursor()
    cur.execute("SELECT content_hash FROM bookmarks WHERE url = ?", ("https://a.com",))
    h = cur.fetchone()[0]
    assert h and len(h) == 16  # non-empty, truncated sha256


def test_rebuild_populates_bookmark_sources(idx):
    """rebuild() must populate bookmark_sources with source='html'."""
    bms = [
        _make_bookmark("https://a.com", "A"),
        _make_bookmark("https://b.com", "B"),
    ]
    idx.rebuild(bms)

    cur = idx.con.cursor()
    cur.execute("SELECT url, source FROM bookmark_sources ORDER BY url")
    rows = cur.fetchall()
    assert len(rows) == 2
    assert rows[0] == ("https://a.com", "html")
    assert rows[1] == ("https://b.com", "html")


def test_rebuild_clears_previous_data(idx):
    """rebuild() should clear old bookmarks and sources before inserting."""
    idx.rebuild([_make_bookmark("https://old.com", "Old")])
    idx.rebuild([_make_bookmark("https://new.com", "New")])

    cur = idx.con.cursor()
    cur.execute("SELECT COUNT(*) FROM bookmarks")
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT url FROM bookmarks")
    assert cur.fetchone()[0] == "https://new.com"
    cur.execute("SELECT COUNT(*) FROM bookmark_sources")
    assert cur.fetchone()[0] == 1


def test_rebuild_empty_list(idx):
    result = idx.rebuild([])
    assert result["indexed"] == 0
    assert idx.is_empty()


def test_rebuild_then_sync_detects_unchanged(idx):
    """rebuild() followed by sync() with the same data should show all unchanged."""
    bms = [_make_bookmark("https://a.com", "A", "Work")]
    idx.rebuild(bms)

    idx.embedder.embed.reset_mock()
    result = idx.sync(bms, source="html")
    assert result.unchanged == 1
    assert result.added == 0
    idx.embedder.embed.assert_not_called()


# ---- stats() tests ----

def test_stats_on_populated_index(idx):
    bms = [
        _make_bookmark("https://github.com/a", "Repo A", "Work"),
        _make_bookmark("https://github.com/b", "Repo B", "Work"),
        _make_bookmark("https://docs.python.org", "Python Docs", "Ref"),
    ]
    idx.rebuild(bms)

    s = idx.stats()
    assert s["total"] == 3
    assert s["model"] is not None
    assert str(idx.db_path) in s["db_path"]
    # github.com should be top domain with count 2
    domains = dict(s["top_domains"])
    assert domains.get("github.com") == 2


def test_stats_on_empty_index(idx):
    s = idx.stats()
    assert s["total"] == 0


# ---- search() tests ----

def test_search_returns_results(idx):
    bms = [
        _make_bookmark("https://a.com", "Alpha"),
        _make_bookmark("https://b.com", "Beta"),
    ]
    idx.rebuild(bms)

    results = idx.search("anything", k=10)
    assert len(results) == 2
    assert all("score" in r for r in results)
    assert all("url" in r for r in results)


def test_search_empty_index(idx):
    results = idx.search("test")
    assert results == []


def test_search_domain_filter(idx):
    bms = [
        _make_bookmark("https://github.com/x", "GitHub"),
        _make_bookmark("https://docs.python.org", "Docs"),
    ]
    idx.rebuild(bms)

    results = idx.search("test", domain="github.com")
    assert all("github.com" in r["domain"] for r in results)


def test_search_folder_filter(idx):
    bms = [
        _make_bookmark("https://a.com", "A", "Work/Internal"),
        _make_bookmark("https://b.com", "B", "Personal"),
    ]
    idx.rebuild(bms)

    results = idx.search("test", folder="work")
    assert all("work" in r["folder_path"].lower() for r in results)


def test_search_k_limit(idx):
    bms = [_make_bookmark(f"https://{i}.com", f"Site {i}") for i in range(20)]
    idx.rebuild(bms)

    results = idx.search("test", k=5)
    assert len(results) == 5


# ---- _remove_source() tests ----

def test_remove_source_cleans_orphans(idx):
    bms = [_make_bookmark("https://a.com", "A")]
    idx.sync(bms, source="chrome:Default")

    removed = idx._remove_source("chrome:Default")
    assert len(removed) == 1
    assert idx.is_empty()


def test_remove_source_preserves_other_sources(idx):
    idx.sync([_make_bookmark("https://a.com", "A")], source="chrome:Default")
    idx.sync([_make_bookmark("https://a.com", "A")], source="firefox:default")

    idx._remove_source("chrome:Default")
    assert not idx.is_empty()  # firefox still references it
