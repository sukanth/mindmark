"""Command-line interface for mindmark."""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .parser import parse_file
from .index import Index, SyncResult, default_db_path, DEFAULT_MODEL


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


def _auto_sync_hint(idx: Index) -> None:
    """Print a hint when the index is empty."""
    if not idx.is_empty():
        return
    print("index is empty — run 'mindmark sync' to import bookmarks from your browsers,")
    print("or run 'mindmark index <bookmarks.html>' to import from an exported file.")
    print()


def _cmd_find(args):
    idx = Index(db_path=args.db)
    if not getattr(args, 'json', False):
        _auto_sync_hint(idx)
    results = idx.search(
        query=args.query, k=args.top,
        domain=args.domain, folder=args.folder,
    )
    if not results:
        print("no results (is the index empty? run: mindmark sync)")
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
    _auto_sync_hint(idx)
    results = idx.search(args.query, k=1)
    if not results:
        print("no results")
        return 1
    webbrowser.open(results[0]["url"])
    print(f"opened: {results[0]['title']}")
    return 0


def _cmd_sync(args):
    from .browsers import collect_all_bookmarks, detect_browsers

    if args.list_browsers:
        profiles = detect_browsers()
        if not profiles:
            print("no supported browsers detected")
            return 1
        print(f"{'Browser':<12} {'Profile':<24} Path")
        print(f"{'-------':<12} {'-------':<24} ----")
        for p in profiles:
            print(f"{p.browser_name:<12} {p.profile_name:<24} {p.bookmark_path}")
        return 0

    print("detecting browsers...")
    pairs = collect_all_bookmarks(browser_filter=args.browser)

    if not pairs:
        if args.browser:
            print(f"no bookmarks found for browser: {args.browser}", file=sys.stderr)
        else:
            print("no supported browsers detected", file=sys.stderr)
        return 1

    idx = Index(db_path=args.db, model_name=args.model)
    total_result = SyncResult()

    for profile, bookmarks in pairs:
        source_id = profile.source_id
        print(f"syncing {profile.browser_name} ({profile.profile_name}): "
              f"{len(bookmarks)} bookmarks...")
        result = idx.sync(bookmarks, source=source_id, batch_size=args.batch_size)
        total_result.added += result.added
        total_result.updated += result.updated
        total_result.removed += result.removed
        total_result.unchanged += result.unchanged
        if result.total_changed > 0:
            print(f"  {result}")

    print(f"\ndone. {total_result}")
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

    psync = sub.add_parser(
        "sync",
        help="sync bookmarks directly from installed browsers (no export needed)",
    )
    psync.add_argument(
        "--browser", type=str, default=None,
        help="sync only this browser (chrome, edge, brave, firefox)",
    )
    psync.add_argument(
        "--list-browsers", action="store_true",
        help="list detected browsers and profiles, then exit",
    )
    psync.add_argument("--model", default=DEFAULT_MODEL)
    psync.add_argument("--batch-size", type=int, default=64)
    psync.set_defaults(func=_cmd_sync)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
