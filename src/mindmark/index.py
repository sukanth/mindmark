"""Embedding + SQLite-backed vector index for bookmarks."""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .parser import Bookmark

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def default_db_path() -> Path:
    base = Path(os.environ.get("MINDMARK_HOME", Path.home() / ".mindmark"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "index.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bookmarks (
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
CREATE INDEX IF NOT EXISTS idx_bookmarks_domain ON bookmarks(domain);
CREATE INDEX IF NOT EXISTS idx_bookmarks_folder ON bookmarks(folder_path);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.executescript(_SCHEMA)
    return con


def _vec_to_blob(v: np.ndarray) -> bytes:
    return v.astype(np.float32).tobytes()


def _blob_to_vec(b: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32, count=dim)


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


@dataclass
class Embedder:
    model_name: str = DEFAULT_MODEL
    _model: object | None = None

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        model = self._load()
        vecs = np.asarray(list(model.embed(texts)), dtype=np.float32)
        return _l2_normalize(vecs)

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]


class Index:
    def __init__(self, db_path: Path | None = None, model_name: str = DEFAULT_MODEL):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.model_name = model_name
        self.con = _connect(self.db_path)
        self.embedder = Embedder(model_name=model_name)

    def rebuild(self, bookmarks: list[Bookmark], batch_size: int = 64) -> dict:
        cur = self.con.cursor()
        cur.execute("DELETE FROM bookmarks")
        cur.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('model', ?)", (self.model_name,))
        self.con.commit()

        total = len(bookmarks)
        if total == 0:
            return {"indexed": 0, "model": self.model_name, "dim": 0}

        rows = []
        for start in range(0, total, batch_size):
            chunk = bookmarks[start:start + batch_size]
            texts = [b.embedding_text() for b in chunk]
            vecs = self.embedder.embed(texts)
            for b, v in zip(chunk, vecs):
                rows.append((
                    b.url, b.title, b.folder_path, b.domain,
                    b.add_date, b.icon, _vec_to_blob(v), int(v.shape[0]),
                ))

        cur.executemany(
            "INSERT OR REPLACE INTO bookmarks "
            "(url, title, folder_path, domain, add_date, icon, embedding, dim) "
            "VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
        self.con.commit()
        return {"indexed": total, "model": self.model_name, "dim": rows[0][-1]}

    def stats(self) -> dict:
        cur = self.con.cursor()
        cur.execute("SELECT COUNT(*) FROM bookmarks")
        total = cur.fetchone()[0]
        cur.execute("SELECT value FROM meta WHERE key='model'")
        m = cur.fetchone()
        cur.execute(
            "SELECT domain, COUNT(*) c FROM bookmarks GROUP BY domain ORDER BY c DESC LIMIT 10"
        )
        top_domains = cur.fetchall()
        cur.execute(
            "SELECT folder_path, COUNT(*) c FROM bookmarks "
            "WHERE folder_path <> '' GROUP BY folder_path ORDER BY c DESC LIMIT 10"
        )
        top_folders = cur.fetchall()
        return {
            "db_path": str(self.db_path),
            "total": total,
            "model": m[0] if m else None,
            "top_domains": top_domains,
            "top_folders": top_folders,
        }

    def _load_matrix(self):
        cur = self.con.cursor()
        cur.row_factory = sqlite3.Row
        cur.execute(
            "SELECT id, url, title, folder_path, domain, add_date, icon, embedding, dim "
            "FROM bookmarks"
        )
        rows = cur.fetchall()
        if not rows:
            return np.zeros((0, 0), dtype=np.float32), []
        dim = rows[0]["dim"]
        mat = np.empty((len(rows), dim), dtype=np.float32)
        for i, r in enumerate(rows):
            mat[i] = _blob_to_vec(r["embedding"], dim)
        return mat, rows

    def search(self, query: str, k: int = 10, domain: str | None = None,
               folder: str | None = None) -> list[dict]:
        mat, rows = self._load_matrix()
        if len(rows) == 0:
            return []
        q = self.embedder.embed_one(query)
        sims = mat @ q
        order = np.argsort(-sims)
        results: list[dict] = []
        for idx in order:
            r = rows[int(idx)]
            if domain and domain.lower() not in r["domain"]:
                continue
            if folder and folder.lower() not in r["folder_path"].lower():
                continue
            results.append({
                "score": float(sims[int(idx)]),
                "title": r["title"],
                "url": r["url"],
                "folder_path": r["folder_path"],
                "domain": r["domain"],
            })
            if len(results) >= k:
                break
        return results
