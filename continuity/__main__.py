import argparse
import json
import sqlite3
import sys

from .core import ContinuityError, Store
from .mcp import TOOLS, call, serve


def main(argv=None):
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="원문 보존 및 AI 세션 인계 도구. ChatGPT 앱 자동 조작 기능은 없습니다.")
    parser.add_argument("--db", default=".continuity/archive.sqlite3", help="Local private database path")
    sub = parser.add_subparsers(dest="command", required=True)
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
    store = Store(args.db)
    try:
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
        store.close()


if __name__ == "__main__":
    sys.exit(main())
