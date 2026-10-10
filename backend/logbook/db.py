import datetime
import json
import shutil
import sqlite3

from .fields import COUNTS, CUSTOM_SLOTS, DURATIONS

_numeric = ",\n    ".join(f"{c} INTEGER NOT NULL DEFAULT 0" for c in DURATIONS + COUNTS)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS aircraft_type (
    code TEXT PRIMARY KEY,
    name TEXT,
    category TEXT NOT NULL DEFAULT 'helicopter' CHECK (category IN ('helicopter', 'aeroplane', 'other')),
    engines TEXT CHECK (engines IN ('single', 'multi')),
    power TEXT CHECK (power IN ('piston', 'turbine')),
    multi_pilot INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS place (
    code TEXT PRIMARY KEY,
    name TEXT,
    kind TEXT,
    lat REAL,
    lon REAL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS flight (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    dep TEXT, arr TEXT, route TEXT,
    type_code TEXT NOT NULL,
    registration TEXT,
    is_sim INTEGER NOT NULL DEFAULT 0,
    sim_device TEXT, sim_level TEXT,
    off_time TEXT, on_time TEXT,
    {_numeric},
    approach_type TEXT,
    pf_pm TEXT CHECK (pf_pm IN ('PF', 'PM')),
    name_pic TEXT, name_copilot TEXT, name_student TEXT, name_instructor TEXT, name_examiner TEXT,
    remarks TEXT, tags TEXT,
    source_row REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS flight_date ON flight (date);

-- Every imported source row, verbatim, so nothing from the original logbook is ever lost.
CREATE TABLE IF NOT EXISTS import_raw (
    source_row INTEGER PRIMARY KEY,
    source_file TEXT,
    data TEXT NOT NULL,
    actions TEXT
);

-- Owner-defined fields: names the uh1-uh5 (hours) and un1-un5 (number) slots on flight.
CREATE TABLE IF NOT EXISTS custom_field (
    slot TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS saved_report (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    spec TEXT NOT NULL
);
"""

# Known types (owner to confirm/edit in the app). code: (name, category, engines, power, multi_pilot)
DEFAULT_TYPES = {
    "R22": ("Robinson R22", "helicopter", "single", "piston", 0),
    "B47G": ("Bell 47G", "helicopter", "single", "piston", 0),
    "B06": ("Bell 206", "helicopter", "single", "turbine", 0),
    "AS50": ("Airbus AS350", "helicopter", "single", "turbine", 0),
    "AS55": ("Airbus AS355", "helicopter", "multi", "turbine", 0),
    "A109": ("Leonardo AW109", "helicopter", "multi", "turbine", 1),
    "S76": ("Sikorsky S-76", "helicopter", "multi", "turbine", 1),
    "A139": ("Leonardo AW139", "helicopter", "multi", "turbine", 1),
    "SIM": ("Generic simulator / training device", "other", None, None, 0),
}


SCHEMA_VERSION = 4
# The two starting user fields (owner request): NVG hours and ship landings.
DEFAULT_CUSTOM = [("uh1", "NVG"), ("un1", "Ship landings")]


def _columns(conn):
    return {r[1] for r in conn.execute("PRAGMA table_info(flight)")}


def _backup(conn, path, reason):
    if path and path != ":memory:" and conn.execute("SELECT COUNT(*) FROM flight").fetchone()[0]:
        conn.commit()
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copyfile(path, f"{path}.before-{reason}-{stamp}")


def migrate(conn, path=None):
    """Bring an older database up to SCHEMA_VERSION. A file copy is kept before any data moves."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        _migrate_v1(conn, path)
    if version < 2:
        _migrate_v2(conn, path)
    if version < 3:
        _migrate_v3(conn, path)
    if version < 4:
        _migrate_v4(conn)


def _migrate_v4(conn):
    """Crew names spelled "Self"/"self " become SELF; PF/PM written as a tag fills the PF/PM field."""
    with conn:
        for col in ("name_pic", "name_copilot", "name_student", "name_instructor", "name_examiner"):
            conn.execute(f"UPDATE flight SET {col} = 'SELF' WHERE upper(trim({col})) = 'SELF' AND {col} != 'SELF'")
        for tag in ("PF", "PM"):
            other = "PM" if tag == "PF" else "PF"
            conn.execute("UPDATE flight SET pf_pm = ? WHERE pf_pm IS NULL "
                         "AND ('|' || upper(tags) || '|') LIKE ? AND ('|' || upper(tags) || '|') NOT LIKE ?",
                         (tag, f"%|{tag}|%", f"%|{other}|%"))
        conn.execute("PRAGMA user_version = 4")


def _migrate_v3(conn, path):
    """SIC entries name the owner as co-pilot (owner decision D21). Only blank co-pilot names are filled."""
    todo = conn.execute("SELECT COUNT(*) FROM flight WHERE sic > 0 AND name_copilot IS NULL").fetchone()[0]
    if todo:
        _backup(conn, path, "sic-copilot-self")
        with conn:
            conn.execute("UPDATE flight SET name_copilot = 'SELF', updated_at = datetime('now') "
                         "WHERE sic > 0 AND name_copilot IS NULL")
    conn.execute("PRAGMA user_version = 3")
    conn.commit()


def _migrate_v2(conn, path):
    """Ship landings that FLYLOG held in its NVG column (small whole numbers; owner decision D20).
    Uses the verbatim import record, so it only touches imported entries and runs once."""
    raw = []
    for source_row, data in conn.execute("SELECT source_row, data FROM import_raw"):
        try:
            value = float(json.loads(data).get("NVG") or 0)
        except ValueError:
            continue
        if 0 < value < 1000 and value.is_integer():
            raw.append((int(value), source_row))
    if raw and conn.execute("SELECT 1 FROM custom_field WHERE slot = 'un1'").fetchone():
        _backup(conn, path, "ship-landings-fix")
        with conn:
            conn.executemany("UPDATE flight SET un1 = un1 + ?, updated_at = datetime('now') "
                             "WHERE source_row = ?", raw)
    conn.execute("PRAGMA user_version = 2")
    conn.commit()


def _migrate_v1(conn, path):
    cols = _columns(conn)
    if "nvg" in cols:
        _backup(conn, path, "user-fields")
    with conn:
        for slot in CUSTOM_SLOTS:
            if slot not in cols:
                conn.execute(f"ALTER TABLE flight ADD COLUMN {slot} INTEGER NOT NULL DEFAULT 0")
        if not conn.execute("SELECT COUNT(*) FROM custom_field").fetchone()[0]:
            conn.executemany("INSERT INTO custom_field (slot, label, position) VALUES (?, ?, ?)",
                             [(slot, label, i) for i, (slot, label) in enumerate(DEFAULT_CUSTOM)])
        # v0 had NVG and ship landings as built-in columns: move them into their user fields
        if "nvg" in cols:
            conn.execute("UPDATE flight SET uh1 = nvg, un1 = ldg_ship")
    for old in ("nvg", "ldg_ship"):
        if old in cols:
            try:
                conn.execute(f"ALTER TABLE flight DROP COLUMN {old}")
            except sqlite3.OperationalError:
                pass  # SQLite < 3.35 cannot drop columns; the old column is simply unused
    conn.execute("PRAGMA user_version = 1")
    conn.commit()


def connect(path):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    migrate(conn, path)
    for code, (name, cat, eng, pwr, mp) in DEFAULT_TYPES.items():
        conn.execute("INSERT OR IGNORE INTO aircraft_type VALUES (?, ?, ?, ?, ?, ?)",
                     (code, name, cat, eng, pwr, mp))
    conn.commit()
    return conn
