"""Command-line interface for mindmark."""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .parser import parse_file
from .index import Index, default_db_path, DEFAULT_MODEL


def _cmd_index(args):
    path = Path(args.path).expanduser()
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2
    print(f"[1/3] parsing {path}")
    bookmarks = parse_file(str(path))
    print(f"      parsed {len(bookmarks)} unique bookmarks")
    print(f"[2/3] loading embedding model ({args.model})")
    idx = Index(db_path=args.db, model_name=args.model)
    print(f"[3/3] embedding + writing index to {idx.db_path}")
    info = idx.rebuild(bookmarks, batch_size=args.batch_size)
    print(f"done. indexed={info['indexed']} dim={info.get('dim','?')} model={info['model']}")
    return 0


def _cmd_find(args):
    idx = Index(db_path=args.db)
    results = idx.search(
        query=args.query, k=args.top,
        domain=args.domain, folder=args.folder,
    )
    if not results:
        print("no results (is the index empty? run: mindmark index <path-to-bookmarks.html>)")
        return 1

    if args.open is not None:
        n = args.open - 1
        if not 0 <= n < len(results):
            print(f"error: --open {args.open} out of range (1..{len(results)})", file=sys.stderr)
            return 2
        webbrowser.open(results[n]["url"])
        print(f"opened: {results[n]['title']}")
        return 0

    if args.json:
        import json
        print(json.dumps(results, indent=2))
        return 0

    for i, r in enumerate(results, 1):
        folder = r["folder_path"] or "(no folder)"
        print(f"{i:>2}. [{r['score']:.3f}] {r['title']}")
        print(f"     {r['url']}")
        print(f"     \u21b3 {folder}")
    return 0


def _cmd_stats(args):
    idx = Index(db_path=args.db)
    s = idx.stats()
    print(f"db:    {s['db_path']}")
    print(f"model: {s['model']}")
    print(f"total: {s['total']} bookmarks")
    if s["top_domains"]:
        print("\ntop domains:")
        for d, c in s["top_domains"]:
            print(f"  {c:5d}  {d}")
    if s["top_folders"]:
        print("\ntop folders:")
        for f, c in s["top_folders"]:
            print(f"  {c:5d}  {f}")
    return 0


def _cmd_open(args):
    idx = Index(db_path=args.db)
    results = idx.search(args.query, k=1)
    if not results:
        print("no results")
        return 1
    webbrowser.open(results[0]["url"])
    print(f"opened: {results[0]['title']}")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="mindmark",
        description="mindmark — local semantic search over your browser bookmarks.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--db", default=os.environ.get("MINDMARK_DB"),
        help=f"SQLite index path (default: {default_db_path()})",
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("index", help="build/refresh the index from an exported bookmarks HTML file")
    pi.add_argument("path", help="path to the exported Netscape bookmarks HTML file")
    pi.add_argument("--model", default=DEFAULT_MODEL)
    pi.add_argument("--batch-size", type=int, default=64)
    pi.set_defaults(func=_cmd_index)

    pf = sub.add_parser("find", help="search bookmarks by natural-language query")
    pf.add_argument("query")
    pf.add_argument("-k", "--top", type=int, default=10)
    pf.add_argument("--domain")
    pf.add_argument("--folder")
    pf.add_argument("--json", action="store_true")
    pf.add_argument("--open", type=int, metavar="N")
    pf.set_defaults(func=_cmd_find)

    ps = sub.add_parser("stats", help="show index stats")
    ps.set_defaults(func=_cmd_stats)

    po = sub.add_parser("open", help="search and open the top result in the browser")
    po.add_argument("query")
    po.set_defaults(func=_cmd_open)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
