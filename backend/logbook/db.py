import sqlite3

from .fields import COUNTS, DURATIONS

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


def connect(path):
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    for code, (name, cat, eng, pwr, mp) in DEFAULT_TYPES.items():
        conn.execute("INSERT OR IGNORE INTO aircraft_type VALUES (?, ?, ?, ?, ?, ?)",
                     (code, name, cat, eng, pwr, mp))
    conn.commit()
    return conn
