import argparse
import json
import sqlite3
from pathlib import Path

from .catalog import connect, ingest, publish, verify


def main():
    parser = argparse.ArgumentParser(description="CookFlow local recipe catalog")
    parser.add_argument("--db", default="data/catalog.sqlite")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    importer = commands.add_parser("import")
    importer.add_argument("files", nargs="+")
    commands.add_parser("list")
    seed_parser = commands.add_parser("seed")
    seed_parser.add_argument("--refresh", action="store_true")
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    release = commands.add_parser("publish")
    release.add_argument("destination")
    check = commands.add_parser("verify")
    check.add_argument("destination")
    args = parser.parse_args()
    try:
        if args.command == "serve":
            import uvicorn
            from .api import create_app
            uvicorn.run(create_app(catalog_path=args.db), host="127.0.0.1", port=args.port)
            return
        if args.command == "seed":
            from .importer import seed
            result = seed(args.db, args.refresh)
        elif args.command == "verify":
            result = verify(args.destination)
        else:
            con = connect(args.db)
            try:
                if args.command == "init":
                    result = {"database": args.db, "schema_version": 1}
                elif args.command == "import":
                    result = [ingest(con, json.loads(Path(p).read_text())) for p in args.files]
                elif args.command == "publish":
                    result = publish(con, args.destination)
                else:
                    result = [{"id": rid, "version": version, "title": json.loads(payload)["title"], "status": json.loads(payload)["status"]} for rid, version, payload in con.execute("SELECT r.id, v.version, v.document FROM recipes r JOIN recipe_versions v ON r.id=v.recipe_id AND r.current_version=v.version ORDER BY r.id")]
            finally:
                con.close()
    except (ValueError, OSError, sqlite3.Error, KeyError) as exc:
        parser.exit(1, f"error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
