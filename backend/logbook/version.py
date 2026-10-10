"""Fingerprint of the code on disk, so the launcher can tell when a running Logbook is out of date."""
import hashlib
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def code_version():
    h = hashlib.sha1()
    files = sorted((ROOT / "backend" / "logbook").glob("*.py"))
    files.append(ROOT / "frontend" / "dist" / "index.html")   # changes whenever the screens are rebuilt
    for f in files:
        if f.exists():
            h.update(f.name.encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:12]
