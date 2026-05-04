from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import sqlite3
import webbrowser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from . import __version__
from ._console import Console
from .defaults import DEFAULT_MODEL, default_db_path

_SUPPORTED_BROWSER_NAMES = {
    "chrome": "Chrome",
    "edge": "Edge",
    "brave": "Brave",
    "firefox": "Firefox",
}
_WRAP_BREAK_AFTER = "/\\?&=#._-"


def _console(args: argparse.Namespace) -> Console:
    existing = getattr(args, "console", None)
    if isinstance(existing, Console):
        return existing
    return Console(color=False if getattr(args, "no_color", False) else None)


def _print_json(console: Console, payload: object, *, preserve_order: bool = False) -> None:
    console.out(json.dumps(payload, indent=2, sort_keys=not preserve_order))


def _is_http_url(url: str) -> bool:
    p = urlparse(url)
    return p.scheme.lower() in {"http", "https"} and bool(p.netloc)


def _check_url_status(url: str, timeout: float) -> tuple[str, int | None, str | None]:
    """Return (url, status_code, error_message)."""
    if not _is_http_url(url):
        return url, None, "skipped (non-http URL)"

    headers = {"User-Agent": "mindmark/0.x (+bookmark-validation)"}
    try:
        req = Request(url, headers=headers, method="HEAD")
        with urlopen(req, timeout=timeout) as resp:
            return url, int(getattr(resp, "status", 0) or 0), None
    except HTTPError as e:
        return url, int(e.code), str(e.reason) if e.reason else "HTTP error"
    except Exception:
        pass

    try:
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=timeout) as resp:
            return url, int(getattr(resp, "status", 0) or 0), None
    except HTTPError as e:
        return url, int(e.code), str(e.reason) if e.reason else "HTTP error"
    except URLError as e:
        return url, None, str(e.reason) if e.reason else "connection error"
    except Exception as e:  # pragma: no cover - defensive fallback
        return url, None, str(e)


def _cmd_validate(args: argparse.Namespace) -> int:
    from .index import Index

    console = _console(args)
    idx = Index(db_path=args.db)
    try:
        bookmarks = idx.all_bookmarks()
        total = len(bookmarks)
        if not bookmarks:
            payload = {
                "checked": 0,
                "healthy": 0,
                "message": "Index is empty. Run 'mindmark sync' to import bookmarks.",
                "skipped": 0,
                "stale": [],
                "stale_count": 0,
                "total": 0,
            }
            if getattr(args, "json", False):
                _print_json(console, payload)
            else:
                console.error(payload["message"])
            return 1

        if not getattr(args, "json", False):
            console.status(f"Validating {total} indexed bookmarks")

        url_to_bm = {b["url"]: b for b in bookmarks}
        stale: list[tuple[dict, int | None, str | None]] = []
        skipped = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {
                ex.submit(_check_url_status, b["url"], args.timeout): b["url"]
                for b in bookmarks
            }
            for fut in concurrent.futures.as_completed(futs):
                url, code, error = fut.result()
                if error == "skipped (non-http URL)":
                    skipped += 1
                    continue
                if code is None or code >= 400:
                    stale.append((url_to_bm[url], code, error))

        checked = total - skipped
        healthy = checked - len(stale)
        stale_items = []
        for bm, code, error in stale:
            reason = f"HTTP {code}" if code is not None else (error or "unreachable")
            stale_items.append(
                {
                    "error": error,
                    "folder_path": bm["folder_path"],
                    "reason": reason,
                    "status_code": code,
                    "title": bm["title"],
                    "url": bm["url"],
                }
            )

        payload = {
            "checked": checked,
            "healthy": healthy,
            "skipped": skipped,
            "stale": stale_items,
            "stale_count": len(stale_items),
            "total": total,
        }
        if getattr(args, "json", False):
            _print_json(console, payload)
            return 0

        summary = (
            f"Checked {checked} bookmarks: healthy={healthy}, "
            f"stale={len(stale)}, skipped={skipped}"
        )
        if not stale:
            console.success(summary)
            return 0

        console.warning(summary)
        console.out()
        console.out(console.style("Stale bookmarks", "bold"))
        for i, item in enumerate(stale_items, 1):
            folder = item["folder_path"] or "(root)"
            console.out(f"{i:2d}. {item['title']}")
            console.out(f"    status: {item['reason']}")
            console.out(f"    url:    {item['url']}")
            console.out(f"    folder: {folder}")
        console.hint("Review or remove stale bookmarks in your browser, then run 'mindmark sync'.")
        return 0
    finally:
        idx.close()


def _cmd_drop_index(args: argparse.Namespace) -> int:
    console = _console(args)
    db_path = Path(args.db).expanduser() if args.db else default_db_path()

    if not db_path.exists():
        console.success(f"Index not found: {db_path}")
        return 0

    if not args.yes:
        try:
            ans = input(f"drop local index at '{db_path}'? [y/N] ").strip().lower()
            if ans != "y":
                console.warning("Cancelled.")
                return 0
        except (EOFError, OSError):
            console.warning("Cancelled.")
            return 0

    try:
        if db_path.is_file():
            db_path.unlink()
        elif db_path.is_dir():
            shutil.rmtree(db_path)
        else:
            console.error(f"Index path is not a file or directory: {db_path}")
            return 1
    except PermissionError as e:
        if db_path.is_file() and _clear_index_contents(db_path):
            console.warning(f"Index file is in use; cleared contents instead: {db_path}")
            return 0
        console.error(f"Failed to remove index: {e}")
        return 1
    except OSError as e:
        console.error(f"Failed to remove index: {e}")
        return 1

    console.success(f"Dropped local index: {db_path}")
    return 0


def _clear_index_contents(db_path: Path) -> bool:
    """Best-effort fallback when index file cannot be deleted due to locks."""
    try:
        con = sqlite3.connect(str(db_path), timeout=1.0)
        cur = con.cursor()
        cur.execute("DELETE FROM bookmark_enrichment")
        cur.execute("DELETE FROM bookmark_sources")
        cur.execute("DELETE FROM bookmarks")
        cur.execute("DELETE FROM meta")
        con.commit()
        con.close()
        return True
    except sqlite3.Error:
        return False


def _cmd_index(args: argparse.Namespace) -> int:
    from .index import Index
    from .parser import parse_file

    console = _console(args)
    path = Path(args.path).expanduser()
    if not path.is_file():
        console.error(f"File not found: {path}")
        return 2

    console.status(f"Parsing bookmarks from {path}")
    bookmarks = parse_file(str(path))
    console.success(f"Parsed {len(bookmarks)} unique bookmarks")
    console.status(f"Loading embedding model: {args.model}")
    idx = Index(db_path=args.db, model_name=args.model)
    try:
        console.status(f"Writing index to {idx.db_path}")
        info = idx.rebuild(bookmarks, batch_size=args.batch_size)
    finally:
        idx.close()
    console.success(
        f"Indexed {info['indexed']} bookmarks "
        f"(dim={info.get('dim', '?')}, model={info['model']})"
    )
    return 0


def _format_score(score: object) -> str:
    try:
        return f"{float(score):.3f}"
    except (TypeError, ValueError):
        return "n/a"


def _display_text(value: object, fallback: str = "") -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return text or fallback


def _find_output_width(console: Console) -> int:
    is_tty = getattr(console.stdout, "isatty", lambda: False)
    if is_tty():
        columns = shutil.get_terminal_size(fallback=(100, 24)).columns
    else:
        columns = 100
    return max(40, min(columns, 160))


def _wrap_cell(text: str, width: int) -> list[str]:
    width = max(1, width)
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = ""
    for word in words:
        if len(word) > width:
            if current:
                lines.append(current)
                current = ""
            chunks = _split_long_token(word, width)
            lines.extend(chunks[:-1])
            current = chunks[-1]
            continue

        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word

    if current:
        lines.append(current)
    return lines or [""]


def _split_long_token(token: str, width: int) -> list[str]:
    chunks: list[str] = []
    remaining = token
    while len(remaining) > width:
        cut = max(remaining.rfind(ch, 1, width + 1) for ch in _WRAP_BREAK_AFTER)
        if cut >= 0:
            cut += 1
        else:
            cut = width
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    chunks.append(remaining)
    return chunks


def _wrap_detail(label: str, value: object, width: int) -> list[str]:
    text = _display_text(value)
    if not text:
        return []

    prefix = f"{label}: "
    content_width = max(1, width - len(prefix))
    chunks = _wrap_cell(text, content_width)
    return [prefix + chunks[0], *[(" " * len(prefix)) + chunk for chunk in chunks[1:]]]


def _find_table_widths(total_width: int, result_count: int) -> tuple[int, int, int]:
    index_width = max(2, len(str(result_count)))
    score_width = len("Score")
    title_width = max(12, total_width - index_width - score_width - 4)
    return index_width, score_width, title_width


def _render_find_results(
    console: Console,
    results: list[dict],
    *,
    query: str,
    include_excerpt: bool,
) -> None:
    width = _find_output_width(console)
    index_width, score_width, title_width = _find_table_widths(
        width,
        len(results),
    )
    detail_indent = " " * (index_width + score_width + 4)
    detail_width = max(20, width - len(detail_indent))

    heading = f"Search results for {query!r} ({len(results)})"
    for line in _wrap_cell(heading, width):
        console.out(console.style(line, "bold"))
    console.out()

    header = (
        f"{'No':>{index_width}}  "
        f"{'Score':<{score_width}}  "
        f"{'Title':<{title_width}}"
    )
    divider = (
        f"{'-' * index_width}  "
        f"{'-' * score_width}  "
        f"{'-' * title_width}"
    )
    console.out(console.style(header.rstrip(), "bold"))
    console.out(divider)

    for i, result in enumerate(results, 1):
        title = _display_text(result["title"], "(untitled)")
        folder = _display_text(result.get("folder_path"), "(root)")
        title_lines = _wrap_cell(title, title_width)

        for line_index, title_part in enumerate(title_lines):
            number = str(i) if line_index == 0 else ""
            score = _format_score(result.get("score")) if line_index == 0 else ""
            row = (
                f"{number:>{index_width}}  "
                f"{score:<{score_width}}  "
                f"{title_part:<{title_width}}"
            )
            console.out(row.rstrip())

        for detail in _wrap_detail("Folder", folder, detail_width):
            console.out(f"{detail_indent}{detail}")
        for detail in _wrap_detail("URL", result["url"], detail_width):
            console.out(f"{detail_indent}{detail}")
        if include_excerpt and result.get("relevant_excerpt"):
            for detail in _wrap_detail("Excerpt", result["relevant_excerpt"], detail_width):
                console.out(f"{detail_indent}{detail}")


def _cmd_find(args: argparse.Namespace) -> int:
    from .index import Index

    console = _console(args)
    idx = Index(db_path=args.db)
    try:
        include_excerpt = getattr(args, "excerpt", False)
        results = idx.search(
            query=args.query,
            k=args.top,
            domain=args.domain,
            folder=args.folder,
            include_excerpt=include_excerpt,
        )
    finally:
        idx.close()

    if not results:
        if getattr(args, "json", False):
            _print_json(console, [], preserve_order=True)
        else:
            console.out("No matching bookmarks. Run 'mindmark sync' to import bookmarks or broaden your query.")
        return 1

    if args.open is not None:
        n = args.open - 1
        if not 0 <= n < len(results):
            console.error(f"--open {args.open} is out of range (1..{len(results)})")
            return 2
        webbrowser.open(results[n]["url"])
        console.success(f"Opened {args.open}. {results[n]['title']}")
        console.out(results[n]["url"])
        return 0

    if getattr(args, "json", False):
        _print_json(console, results, preserve_order=True)
        return 0

    _render_find_results(
        console,
        results,
        query=args.query,
        include_excerpt=include_excerpt,
    )
    console.hint(f"Open a result with: mindmark find {args.query!r} --open N")
    return 0


def _cmd_open(args: argparse.Namespace) -> int:
    args.open = 1
    args.json = False
    return _cmd_find(args)


def _stable_stats(stats: dict) -> dict:
    return {
        "db_path": stats["db_path"],
        "model": stats["model"],
        "top_domains": [
            {"count": count, "domain": domain}
            for domain, count in stats.get("top_domains", [])
        ],
        "top_folders": [
            {"count": count, "folder": folder}
            for folder, count in stats.get("top_folders", [])
        ],
        "total": stats["total"],
    }


def _cmd_stats(args: argparse.Namespace) -> int:
    from .index import Index

    console = _console(args)
    idx = Index(db_path=args.db)
    try:
        stats = _stable_stats(idx.stats())
    finally:
        idx.close()

    if getattr(args, "json", False):
        _print_json(console, stats)
        return 0

    console.out(f"Bookmarks: {console.style(str(stats['total']), 'accent')}")
    console.out(f"Index:     {stats['db_path']}")
    if stats["model"]:
        console.out(f"Model:     {stats['model']}")
    if stats["total"] == 0:
        console.hint("Run 'mindmark sync' to import bookmarks from your browsers.")
        return 0

    if stats["top_domains"]:
        console.out()
        console.out(console.style("Top domains", "bold"))
        for item in stats["top_domains"]:
            console.out(f"  {item['domain']}: {item['count']}")
    if stats["top_folders"]:
        console.out()
        console.out(console.style("Top folders", "bold"))
        for item in stats["top_folders"]:
            console.out(f"  {item['folder']}: {item['count']}")
    return 0


def _cmd_enrich(args: argparse.Namespace) -> int:
    from .enricher import enrich_pending
    from .index import Index

    console = _console(args)
    idx = Index(db_path=args.db)
    try:
        pending = idx.pending_enrichment_urls(
            limit=None if args.refresh_failed else args.limit
        )
        reset = 0
        if args.refresh_failed:
            reset = idx.reset_failed_enrichment()
            pending = idx.pending_enrichment_urls(limit=args.limit)

        before = idx.enrichment_stats()
        if not pending:
            payload = {
                "before": before,
                "complete": 0,
                "failed": 0,
                "pending": 0,
                "reset_failed": reset,
                "skipped": 0,
                "status": "idle",
                "total": 0,
            }
            if getattr(args, "json", False):
                _print_json(console, payload)
            else:
                console.out("Nothing to enrich. Run 'mindmark sync' first, or use --refresh-failed.")
            return 0

        if not getattr(args, "json", False):
            console.status(
                f"Enriching {len(pending)} bookmarks "
                f"(pending={before.get('pending', 0)}, workers={args.workers}, timeout={args.timeout}s)"
            )

        result = enrich_pending(
            idx,
            limit=args.limit,
            workers=args.workers,
            timeout=args.timeout,
            refresh_failed=False,
        )
        after = idx.enrichment_stats()
        payload = {
            "after": after,
            "before": before,
            "complete": result.complete,
            "failed": result.failed,
            "reset_failed": reset,
            "skipped": result.skipped,
            "status": "complete",
            "total": result.total,
        }
        if getattr(args, "json", False):
            _print_json(console, payload)
        else:
            console.success(
                f"Enrichment complete: complete={result.complete}, "
                f"failed={result.failed}, skipped={result.skipped}"
            )
        return 0
    finally:
        idx.close()


def _browser_profile_dict(profile: object) -> dict:
    return {
        "browser": getattr(profile, "browser_name"),
        "path": str(getattr(profile, "bookmark_path")),
        "profile": getattr(profile, "profile_name"),
        "source_id": getattr(profile, "source_id"),
        "type": getattr(profile, "browser_type"),
    }


def _detect_profiles(browser: str | None) -> list[object]:
    from .browsers.paths import detect_browsers

    profiles = detect_browsers()
    if browser:
        wanted = browser.lower()
        profiles = [p for p in profiles if p.browser_name.lower() == wanted]
    return profiles


def _list_browsers(args: argparse.Namespace) -> int:
    console = _console(args)
    profiles = _detect_profiles(getattr(args, "browser", None))
    payload = {
        "detected": [_browser_profile_dict(p) for p in profiles],
        "supported": list(_SUPPORTED_BROWSER_NAMES.values()),
    }
    if getattr(args, "json", False):
        _print_json(console, payload)
        return 0

    console.out(console.style("Supported browsers", "bold"))
    for name in payload["supported"]:
        console.out(f"  - {name}")
    if profiles:
        console.out()
        console.out(console.style("Detected profiles", "bold"))
        for profile in profiles:
            console.out(
                f"  - {profile.browser_name} ({profile.profile_name}) "
                f"→ {profile.bookmark_path}"
            )
    else:
        console.out()
        console.out("Detected profiles: none")
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    from .browsers import parse_browser_bookmarks

    console = _console(args)
    if args.list_browsers:
        return _list_browsers(args)

    profiles = _detect_profiles(args.browser)
    if not profiles:
        target = _SUPPORTED_BROWSER_NAMES.get(args.browser or "", "supported browsers")
        message = f"No bookmark files detected for {target}."
        payload = {
            "error": message,
            "profiles": [],
            "supported": list(_SUPPORTED_BROWSER_NAMES.values()),
        }
        if getattr(args, "json", False):
            _print_json(console, payload)
        else:
            console.error(message)
            console.hint("Use 'mindmark sync --list-browsers' to see supported browsers.", stderr=True)
        return 1

    if not getattr(args, "json", False):
        names = ", ".join(f"{p.browser_name} ({p.profile_name})" for p in profiles)
        console.status(f"Reading bookmarks from {names}")

    parsed: list[tuple[object, list[object]]] = []
    warnings: list[dict] = []
    for profile in profiles:
        try:
            bookmarks = parse_browser_bookmarks(profile)
        except (OSError, ValueError, KeyError, json.JSONDecodeError, sqlite3.Error) as exc:
            warning = {
                "browser": profile.browser_name,
                "error": str(exc),
                "profile": profile.profile_name,
            }
            warnings.append(warning)
            if not getattr(args, "json", False):
                console.warning(
                    f"Skipped {profile.browser_name} ({profile.profile_name}): {exc}"
                )
            continue
        parsed.append((profile, bookmarks))

    if not parsed:
        payload = {
            "error": "No readable browser bookmark profiles were found.",
            "profiles": [],
            "summary": {"added": 0, "removed": 0, "unchanged": 0, "updated": 0},
            "warnings": warnings,
        }
        if getattr(args, "json", False):
            _print_json(console, payload)
        else:
            console.error(payload["error"])
            console.hint("Close browsers that may be locking bookmark files, then retry.", stderr=True)
        return 1

    total_bookmarks = sum(len(bookmarks) for _profile, bookmarks in parsed)
    if not getattr(args, "json", False):
        console.success(f"Collected {total_bookmarks} bookmarks from {len(parsed)} profile(s)")
        console.status(f"Syncing index at {args.db or default_db_path(create=False)}")

    from .index import Index

    idx = Index(db_path=args.db, model_name=args.model)
    try:
        summary = {"added": 0, "removed": 0, "unchanged": 0, "updated": 0}
        profile_results = []
        for profile, bookmarks in parsed:
            res = idx.sync(bookmarks, source=profile.source_id)
            item = _browser_profile_dict(profile)
            item.update(
                {
                    "bookmarks": len(bookmarks),
                    "added": res.added,
                    "removed": res.removed,
                    "unchanged": res.unchanged,
                    "updated": res.updated,
                }
            )
            profile_results.append(item)
            summary["added"] += res.added
            summary["removed"] += res.removed
            summary["unchanged"] += res.unchanged
            summary["updated"] += res.updated
        payload = {
            "db_path": str(idx.db_path),
            "model": idx.model_name,
            "profiles": profile_results,
            "summary": summary,
            "warnings": warnings,
        }
    finally:
        idx.close()

    if getattr(args, "json", False):
        _print_json(console, payload)
    else:
        console.success(
            "Sync complete: "
            f"added={summary['added']}, updated={summary['updated']}, "
            f"removed={summary['removed']}, unchanged={summary['unchanged']}"
        )
        if summary["added"] or summary["updated"]:
            console.hint("Run 'mindmark find \"your query\"' to search your bookmarks.")
    return 0


def _add_search_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("query")
    parser.add_argument("-k", "--top", type=int, default=10)
    parser.add_argument("--domain")
    parser.add_argument("--folder")
    parser.add_argument(
        "--excerpt",
        action="store_true",
        help="include excerpt from enriched page content (requires mindmark enrich)",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mindmark",
        description="mindmark - local semantic search over your browser bookmarks.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--db",
        default=os.environ.get("MINDMARK_DB"),
        help=f"SQLite index path (default: {default_db_path(create=False)})",
    )
    p.add_argument("--no-color", action="store_true", help="disable ANSI color output")

    sub = p.add_subparsers(dest="cmd")

    pi = sub.add_parser("index", help="build/refresh the index from an exported bookmarks HTML file")
    pi.add_argument("path", help="path to the exported Netscape bookmarks HTML file")
    pi.add_argument("--model", default=DEFAULT_MODEL)
    pi.add_argument("--batch-size", type=int, default=64)
    pi.set_defaults(func=_cmd_index)

    pf = sub.add_parser("find", help="search bookmarks by natural-language query")
    _add_search_options(pf)
    pf.add_argument("--json", action="store_true")
    pf.add_argument("--open", type=int, metavar="N")
    pf.set_defaults(func=_cmd_find)

    po = sub.add_parser("open", help="open the top bookmark matching a query")
    _add_search_options(po)
    po.set_defaults(func=_cmd_open)

    ps = sub.add_parser("stats", help="show index stats")
    ps.add_argument("--json", action="store_true")
    ps.set_defaults(func=_cmd_stats)

    py = sub.add_parser("sync", help="automatically sync bookmarks from local browsers")
    py.add_argument("--model", default=DEFAULT_MODEL)
    py.add_argument(
        "--browser",
        choices=sorted(_SUPPORTED_BROWSER_NAMES),
        type=str.lower,
        help="sync only one browser: chrome, edge, brave, or firefox",
    )
    py.add_argument("--list-browsers", action="store_true", help="list supported and detected browsers")
    py.add_argument("--json", action="store_true")
    py.set_defaults(func=_cmd_sync)

    pv = sub.add_parser("validate", help="validate indexed bookmark URLs and report stale entries (read-only)")
    pv.add_argument("--timeout", type=float, default=8.0, help="per-request timeout in seconds (default: 8.0)")
    pv.add_argument("--workers", type=int, default=16, help="parallel request workers (default: 16)")
    pv.add_argument("--json", action="store_true")
    pv.set_defaults(func=_cmd_validate)

    pd = sub.add_parser("drop-index", help="drop (delete) the local index database")
    pd.add_argument("--yes", action="store_true", help="auto-confirm index deletion")
    pd.set_defaults(func=_cmd_drop_index)

    pe = sub.add_parser(
        "enrich",
        help="fetch page content for bookmarks and build summary embeddings (local, no cloud)",
    )
    pe.add_argument("--limit", type=int, default=None, help="max bookmarks to process per run (default: all pending)")
    pe.add_argument("--workers", type=int, default=8, help="parallel fetch workers (default: 8)")
    pe.add_argument("--timeout", type=float, default=10.0, help="per-request fetch timeout in seconds (default: 10.0)")
    pe.add_argument("--refresh-failed", action="store_true", help="retry previously failed enrichments")
    pe.add_argument("--json", action="store_true")
    pe.set_defaults(func=_cmd_enrich)

    return p


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.cmd == "validate":
        if args.timeout <= 0:
            parser.error("--timeout must be > 0")
        if args.workers <= 0:
            parser.error("--workers must be > 0")
    elif args.cmd == "enrich":
        if args.workers <= 0:
            parser.error("--workers must be > 0")
        if args.timeout <= 0:
            parser.error("--timeout must be > 0")
        if args.limit is not None and args.limit <= 0:
            parser.error("--limit must be > 0")
    elif args.cmd in {"find", "open"}:
        if args.top <= 0:
            parser.error("--top must be > 0")
        if getattr(args, "open", None) is not None and args.open <= 0:
            parser.error("--open must be > 0")
    elif args.cmd == "index":
        if args.batch_size <= 0:
            parser.error("--batch-size must be > 0")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd is None:
        parser.print_help()
        return 2

    _validate_args(parser, args)
    args.console = Console(color=False if args.no_color else None)

    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        args.console.error("Cancelled by user.")
        return 130
    except BrokenPipeError:
        return 1
    except (sqlite3.Error, OSError, RuntimeError, ImportError, ValueError) as exc:
        args.console.error(str(exc) or exc.__class__.__name__)
        args.console.hint("Re-run with a valid index path or retry after closing locked files.", stderr=True)
        return 1
