"""Command line: python -m logbook serve | import <export.xlsx> [--corrections file.json] [--replace]"""
import argparse
import json
import os
import signal
import socket
import subprocess
import time
import urllib.request
import webbrowser

from . import api, db, importer, version


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
        if port_in_use(args.host, args.port):
            running = running_version(url)
            if running == version.code_version():
                print(f"The Logbook is already running at {url} - opening it.")
                if not args.no_browser:
                    webbrowser.open(url)
                return
            if running is not None:
                # An older copy is still running (e.g. started before a git pull): restart it with the update
                print("Restarting the Logbook to apply the update...")
                if not stop_running(url, args.host, args.port):
                    raise SystemExit('The old Logbook would not stop. Run:  pkill -f "logbook serve"  and try again.')
            else:
                raise SystemExit(f"Port {args.port} is being used by another program.\n"
                                 f"Start the Logbook on a different port instead:  ./logbook.sh serve --port {args.port + 1}")
        print(f"Logbook running at {url}  (database: {args.db})  - Ctrl+C to stop")
        if not args.no_browser:
            webbrowser.open(url)
        uvicorn.run(api.create_app(args.db), host=args.host, port=args.port, log_level="warning")


def port_in_use(host, port):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)   # as uvicorn does
        try:
            s.bind((host, port))
        except OSError:
            return True
    return False


_local = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never via a proxy


def running_version(url):
    """Code version of the Logbook answering at url ("" if it predates versioning), or None if it isn't one."""
    try:
        with _local.open(f"{url}/api/meta", timeout=2) as r:
            meta = json.load(r)
    except Exception:
        return None
    return meta.get("code_version", "") if "custom_fields" in meta else None


def stop_running(url, host, port):
    try:
        _local.open(urllib.request.Request(f"{url}/api/shutdown", method="POST"), timeout=3).close()
    except Exception:   # a copy older than the shutdown endpoint: stop it by its process instead
        found = subprocess.run(["pgrep", "-f", "[-]m logbook .*serve"], capture_output=True, text=True).stdout.split()
        for pid in {int(p) for p in found} - {os.getpid(), os.getppid()}:   # never this launcher itself
            try:
                os.kill(pid, signal.SIGINT)
            except OSError:
                pass
    for _ in range(50):
        if not port_in_use(host, port):
            return True
        time.sleep(0.2)
    return False


if __name__ == "__main__":
    main()
