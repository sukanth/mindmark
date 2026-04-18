"""Parse Firefox bookmarks from ``places.sqlite``.

Firefox stores bookmarks in an SQLite database.  The browser holds a lock
on the file while running, so we **copy** it (including WAL/SHM files) to
a temporary directory before reading.
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

from ..parser import Bookmark

# Firefox bookmark types (moz_bookmarks.type)
_TYPE_BOOKMARK = 1
_TYPE_FOLDER = 2

# Built-in root folder IDs to skip as folder-path components
_ROOT_IDS = {1, 2, 3, 4, 5, 6}  # root, menu, toolbar, tags, unfiled, mobile


def parse_firefox_places(path: Path) -> list[Bookmark]:
    """Parse bookmarks from a Firefox ``places.sqlite`` file.

    Uses SQLite's backup API to create a consistent snapshot, which is
    safer than filesystem copies when Firefox is running (especially on
    Windows where file locking is stricter).
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Firefox places.sqlite not found: {path}")

    with tempfile.TemporaryDirectory(prefix="mindmark_ff_") as tmpdir:
        dst = Path(tmpdir) / "places.sqlite"
        try:
            # SQLite backup API: creates a consistent snapshot even with WAL
            src_con = sqlite3.connect(
                path.resolve().as_uri() + "?mode=ro", uri=True
            )
            dst_con = sqlite3.connect(str(dst))
            src_con.backup(dst_con)
            src_con.close()
            dst_con.close()
        except (sqlite3.OperationalError, OSError):
            # Fallback: filesystem copy if backup fails (e.g. locked by OS)
            shutil.copy2(path, dst)
            for suffix in ("-wal", "-shm"):
                sidecar = path.parent / (path.name + suffix)
                if sidecar.is_file():
                    try:
                        shutil.copy2(sidecar, Path(tmpdir) / (dst.name + suffix))
                    except OSError:
                        pass

        return _read_places(dst)


def _read_places(db_path: Path) -> list[Bookmark]:
    """Read bookmarks from a copied places.sqlite."""
    # Use Path.as_uri() for Windows-safe URI (handles drive letters, spaces)
    uri = db_path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    try:
        return _query_bookmarks(con)
    finally:
        con.close()


def _build_folder_map(con: sqlite3.Connection) -> dict[int, str]:
    """Build a mapping from folder id → full folder path string."""
    cur = con.execute(
        "SELECT id, parent, title, type FROM moz_bookmarks WHERE type = ?",
        (_TYPE_FOLDER,),
    )
    folders: dict[int, tuple[int, str]] = {}
    for row in cur:
        fid = row["id"]
        parent = row["parent"]
        title = row["title"] or ""
        folders[fid] = (parent, title)

    # Resolve full paths by walking up parent chain
    cache: dict[int, str] = {}

    def resolve(fid: int) -> str:
        if fid in cache:
            return cache[fid]
        if fid not in folders or fid in _ROOT_IDS:
            cache[fid] = ""
            return ""
        parent_id, title = folders[fid]
        parent_path = resolve(parent_id)
        if parent_path:
            full = f"{parent_path}/{title}" if title else parent_path
        else:
            full = title
        cache[fid] = full
        return full

    return {fid: resolve(fid) for fid in folders}


def _query_bookmarks(con: sqlite3.Connection) -> list[Bookmark]:
    """Query bookmarks from a places.sqlite connection."""
    folder_map = _build_folder_map(con)

    cur = con.execute("""
        SELECT b.id, b.title, b.parent, b.dateAdded,
               p.url
        FROM moz_bookmarks b
        JOIN moz_places p ON b.fk = p.id
        WHERE b.type = ?
          AND p.url IS NOT NULL
          AND p.url NOT LIKE 'place:%'
    """, (_TYPE_BOOKMARK,))

    seen: set[str] = set()
    bookmarks: list[Bookmark] = []

    for row in cur:
        url = row["url"]
        if not url or url in seen:
            continue
        seen.add(url)

        title = row["title"] or url
        parent_id = row["parent"]
        folder_path = folder_map.get(parent_id, "")

        try:
            # Firefox stores dates as microseconds since epoch
            add_date = int(row["dateAdded"] or 0)
        except (ValueError, TypeError):
            add_date = 0

        bookmarks.append(Bookmark(
            title=title,
            url=url,
            folder_path=folder_path,
            add_date=add_date,
            icon=None,
        ))

    return bookmarks
