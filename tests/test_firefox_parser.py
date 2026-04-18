"""Tests for the Firefox places.sqlite bookmark parser."""
import sqlite3
import tempfile
from pathlib import Path

from mindmark.browsers.firefox import parse_firefox_places


def _create_places_db() -> Path:
    """Create a minimal Firefox places.sqlite with test bookmarks."""
    tmp = tempfile.NamedTemporaryFile(
        suffix=".sqlite", delete=False, prefix="mindmark_test_ff_"
    )
    tmp.close()
    db_path = Path(tmp.name)

    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE moz_places (
            id INTEGER PRIMARY KEY,
            url TEXT
        );
        CREATE TABLE moz_bookmarks (
            id INTEGER PRIMARY KEY,
            type INTEGER,
            fk INTEGER,
            parent INTEGER,
            title TEXT,
            dateAdded INTEGER
        );

        -- Root folders (IDs 1-6 are built-in roots)
        INSERT INTO moz_bookmarks (id, type, fk, parent, title) VALUES
            (1, 2, NULL, 0, 'root'),
            (2, 2, NULL, 1, 'menu'),
            (3, 2, NULL, 1, 'toolbar'),
            (4, 2, NULL, 1, 'tags'),
            (5, 2, NULL, 1, 'unfiled'),
            (6, 2, NULL, 1, 'mobile');

        -- User folders
        INSERT INTO moz_bookmarks (id, type, fk, parent, title) VALUES
            (100, 2, NULL, 3, 'Work'),
            (101, 2, NULL, 100, 'Internal');

        -- Places (URLs)
        INSERT INTO moz_places (id, url) VALUES
            (1, 'https://docs.python.org/3/'),
            (2, 'https://github.com'),
            (3, 'https://eng.ms/docs/kusto'),
            (4, 'https://stackoverflow.com');

        -- Bookmarks referencing places
        INSERT INTO moz_bookmarks (id, type, fk, parent, title, dateAdded) VALUES
            (200, 1, 1, 3, 'Python Docs', 1700000000000000),
            (201, 1, 2, 100, 'GitHub', 1700000000000001),
            (202, 1, 3, 101, 'Kusto Guide', 1700000000000002),
            (203, 1, 4, 5, 'Stack Overflow', 1700000000000003);
    """)
    con.close()
    return db_path


def test_parses_urls_and_titles():
    path = _create_places_db()
    bms = parse_firefox_places(path)
    by_url = {b.url: b for b in bms}
    assert "https://docs.python.org/3/" in by_url
    assert by_url["https://docs.python.org/3/"].title == "Python Docs"
    assert "https://github.com" in by_url
    assert "https://stackoverflow.com" in by_url
    path.unlink()


def test_folder_paths():
    path = _create_places_db()
    bms = parse_firefox_places(path)
    by_url = {b.url: b for b in bms}
    # toolbar > Work
    assert by_url["https://github.com"].folder_path == "Work"
    # toolbar > Work > Internal
    assert by_url["https://eng.ms/docs/kusto"].folder_path == "Work/Internal"
    path.unlink()


def test_skips_place_urls():
    """Firefox internal place: URLs should be excluded."""
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT);
        CREATE TABLE moz_bookmarks (
            id INTEGER PRIMARY KEY, type INTEGER, fk INTEGER,
            parent INTEGER, title TEXT, dateAdded INTEGER
        );
        INSERT INTO moz_bookmarks (id, type, fk, parent, title) VALUES
            (1, 2, NULL, 0, 'root'),
            (2, 2, NULL, 1, 'menu');
        INSERT INTO moz_places (id, url) VALUES
            (1, 'place:sort=8&maxResults=10'),
            (2, 'https://example.com');
        INSERT INTO moz_bookmarks (id, type, fk, parent, title, dateAdded) VALUES
            (100, 1, 1, 2, 'Recent Tags', 0),
            (101, 1, 2, 2, 'Example', 0);
    """)
    con.close()
    bms = parse_firefox_places(db_path)
    urls = [b.url for b in bms]
    assert "https://example.com" in urls
    assert not any(u.startswith("place:") for u in urls)
    db_path.unlink()


def test_deduplicates_by_url():
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT);
        CREATE TABLE moz_bookmarks (
            id INTEGER PRIMARY KEY, type INTEGER, fk INTEGER,
            parent INTEGER, title TEXT, dateAdded INTEGER
        );
        INSERT INTO moz_bookmarks (id, type, fk, parent, title) VALUES
            (1, 2, NULL, 0, 'root'), (2, 2, NULL, 1, 'menu');
        INSERT INTO moz_places (id, url) VALUES (1, 'https://example.com');
        INSERT INTO moz_bookmarks (id, type, fk, parent, title, dateAdded) VALUES
            (100, 1, 1, 2, 'Example A', 0),
            (101, 1, 1, 2, 'Example B', 0);
    """)
    con.close()
    bms = parse_firefox_places(db_path)
    assert len([b for b in bms if b.url == "https://example.com"]) == 1
    db_path.unlink()
