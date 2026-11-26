import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .core import ContinuityError, Store
from .mcp import TOOLS, call, serve
from .estimator import DEFAULT_LIMITS, estimate_handoff, format_report
from .tokenizers import prepare_tokenizers


def estimate_files(args):
    inputs = [*args.original, *args.inserted, *args.followup]
    if args.output and any(Path(args.output).resolve() == Path(p).resolve() for p in inputs):
        raise ContinuityError("Output must not overwrite an input file")
    byte_sizes = {}

    def read_group(paths, group):
        texts, sizes = [], []
        for i, path in enumerate(paths, 1):
            try:
                # Preserve CRLF; strip only a leading UTF-8 BOM. No JSON parsing,
                # branch selection, attachment extraction or network access.
                data = Path(path).read_bytes()
                text = data.decode("utf-8-sig")
                if "\x00" in text:
                    raise ValueError("binary input")
            except (OSError, UnicodeError, ValueError) as exc:
                raise ContinuityError(f"Cannot read {group} input #{i} as UTF-8 text; use TXT/MD/JSON/code, not ZIP/PDF") from exc
            texts.append(text)
            sizes.append(len(data))
        byte_sizes[group] = sizes
        return texts

    result = estimate_handoff(
        read_group(args.original, "original"), read_group(args.inserted, "inserted"),
        read_group(args.followup, "followup"), context_limits=args.limits,
        overhead_min=args.overhead[0], overhead_max=args.overhead[1],
        next_turn_reserve=args.reserve, mode=args.mode, tokenizer_dir=args.tokenizer_dir,
    )
    result["input_file_bytes"] = byte_sizes
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        try:
            # Exclusive creation also prevents hard-link/symlink input overwrite.
            with open(args.output, "x", encoding="utf-8", newline="\n") as f:
                f.write(payload + "\n")
        except OSError as exc:
            raise ContinuityError("Cannot create output: choose a new filename in an existing folder") from exc
    print(payload if args.json else format_report(result))
    return 0


def main(argv=None):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="원문 보존 및 AI 세션 인계 도구. ChatGPT 앱 자동 조작 기능은 없습니다.")
    parser.add_argument("--db", default=".continuity/archive.sqlite3", help="Local private database path")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("estimate-capacity", help="Local handoff token estimate; no native ChatGPT telemetry")
    p.add_argument("--original", action="append", required=True, help="Full original archive text file (repeatable)")
    p.add_argument("--inserted", action="append", required=True, help="Text actually retained in new context (repeatable)")
    p.add_argument("--followup", action="append", default=[], help="Retained response/summary/tool text (repeatable)")
    p.add_argument("--limits", type=int, nargs="+", default=list(DEFAULT_LIMITS), help="Hypothetical limits, not model specs")
    p.add_argument("--overhead", type=int, nargs=2, default=[0, 0], metavar=("MIN", "MAX"), help="Assumed additional current tokens; default excludes them")
    p.add_argument("--reserve", type=int, default=0, help="Next-turn reserve; not current usage")
    p.add_argument("--mode", choices=["auto", "bpe", "heuristic"], default="auto")
    p.add_argument("--tokenizer-dir", help="Optional LOCAL vocabulary directory")
    p.add_argument("--json", action="store_true", help="Print numeric JSON without source contents or filenames")
    p.add_argument("--output", help="Save JSON to a new local file; existing files are never overwritten")
    p = sub.add_parser("prepare-tokenizers", help="Explicit setup: download public vocabularies only (no conversation input)")
    p.add_argument("--tokenizer-dir")
    p = sub.add_parser("import", help="Import ChatGPT export JSON or normalized conversation JSON")
    p.add_argument("project")
    p.add_argument("file")
    sub.add_parser("list")
    p = sub.add_parser("snapshot")
    p.add_argument("project")
    p.add_argument("--order", nargs="+", required=True, help="Every room id in intended chronological order")
    p.add_argument("--chunk-chars", type=int, default=8000)
    p.add_argument("--assets", help="Optional asset manifest JSON list")
    p = sub.add_parser("asset")
    p.add_argument("file")
    p = sub.add_parser("checks", help="Load independently authored regression questions; local operator only")
    p.add_argument("snapshot")
    p.add_argument("file")
    p = sub.add_parser("export-source")
    p.add_argument("sha256")
    p.add_argument("destination")
    p = sub.add_parser("call", help="Execute same named function exposed through MCP")
    p.add_argument("name", choices=[t["name"] for t in TOOLS])
    p.add_argument("--args", default="{}", help="JSON arguments or @path/to/arguments.json")
    sub.add_parser("mcp", help="Start stdio MCP server for a compatible local AI client")
    args = parser.parse_args(argv)
    store = None
    try:
        if args.command == "estimate-capacity":
            return estimate_files(args)
        if args.command == "prepare-tokenizers":
            print(json.dumps(prepare_tokenizers(args.tokenizer_dir)))
            return 0
        store = Store(args.db)
        def load(path):
            with open(path, encoding="utf-8-sig") as f:
                return json.load(f)
        if args.command == "import":
            result = store.import_file(args.project, args.file)
        elif args.command == "list":
            result = store.list_projects()
        elif args.command == "snapshot":
            result = store.snapshot(args.project, args.order, args.chunk_chars, load(args.assets) if args.assets else None)
        elif args.command == "asset":
            result = store.put_asset(args.file)
        elif args.command == "checks":
            result = store.add_checks(args.snapshot, load(args.file))
        elif args.command == "export-source":
            result = store.export_source(args.sha256, args.destination)
        elif args.command == "call":
            kwargs = load(args.args[1:]) if args.args.startswith("@") else json.loads(args.args)
            result = call(store, args.name, kwargs)
        else:
            serve(store)
            return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ContinuityError, OSError, ValueError, sqlite3.Error, KeyError, TypeError) as e:
        print(str(e), file=sys.stderr)
        return 2
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    sys.exit(main())
