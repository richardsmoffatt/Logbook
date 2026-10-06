"""Command line: python -m logbook serve | import <export.xlsx> [--corrections file.json] [--replace]"""
import argparse
import os
import webbrowser

from . import api, db, importer


def main():
    parser = argparse.ArgumentParser(prog="logbook")
    parser.add_argument("--db", default=os.environ.get("LOGBOOK_DB") or str(api.DEFAULT_DB),
                        help="database file (default: data/logbook.db)")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the app in your browser")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to reach it from other devices")
    serve.add_argument("--no-browser", action="store_true")
    imp = sub.add_parser("import", help="import a FLYLOG Excel export")
    imp.add_argument("export")
    imp.add_argument("--corrections")
    imp.add_argument("--replace", action="store_true", help="replace a previous import")
    args = parser.parse_args()

    if args.command == "import":
        os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
        conn = db.connect(args.db)
        fixes = importer.load_corrections(args.corrections) if args.corrections else None
        if not args.replace and conn.execute("SELECT COUNT(*) FROM flight WHERE source_row IS NOT NULL").fetchone()[0]:
            raise SystemExit("A logbook has already been imported; use --replace to re-import it.")
        result = importer.import_export(conn, args.export, fixes, replace=args.replace)
        for problem in result["invalid"]:
            print(f"Row {problem['row']} ({problem['date']}): {'; '.join(problem['errors'])}")
        if result["invalid"]:
            raise SystemExit(f"{len(result['invalid'])} invalid entries - nothing was imported.")
        print(f"Read {result['read']} rows: imported {result['imported']} entries "
              f"({result['corrected']} corrected, {result['split']} split, {result['deleted']} deleted).")
    else:
        import uvicorn
        url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
        print(f"Logbook running at {url}  (database: {args.db})  - Ctrl+C to stop")
        if not args.no_browser:
            webbrowser.open(url)
        uvicorn.run(api.create_app(args.db), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
