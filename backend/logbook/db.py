import datetime
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


SCHEMA_VERSION = 1
# The two starting user fields (owner request): NVG hours and ship landings.
DEFAULT_CUSTOM = [("uh1", "NVG"), ("un1", "Ship landings")]


def _columns(conn):
    return {r[1] for r in conn.execute("PRAGMA table_info(flight)")}


def migrate(conn, path=None):
    """Bring an older database up to SCHEMA_VERSION. A file copy is kept before any data moves."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return
    cols = _columns(conn)
    if "nvg" in cols and path and path != ":memory:" and conn.execute("SELECT COUNT(*) FROM flight").fetchone()[0]:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        conn.commit()
        shutil.copyfile(path, f"{path}.before-user-fields-{stamp}")
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
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
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
