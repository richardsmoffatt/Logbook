"""Import a FLYLOG Excel export, applying an owner-maintained corrections file.

The corrections file (JSON) holds personal data and lives outside the repository. Format:

{
  "rules": {
    "nvg_milliseconds": true,          # NVG column is in ms; values below the threshold are ignored
    "nvg_ignore_below": 1000,
    "sim_registrations": ["AUH139"],   # registrations that are simulator sessions
    "sim_devices": {"AW-139": {"type": "A139", "level": "D"}, "Generic": {"type": "SIM"}},
    "sim_default_device": "Generic",   # device for sims with no SIMULATOR_TYPE
    "level_d_counts_as_flight_time": true,
    "ifr_fill_split": true,            # unsplit IFR -> actual (aircraft) / simulated (sim)
    "user_fields": {"NVG": "uh1", "SHIPS": "un1"}   # FLYLOG column -> user field slot (these are the defaults)
  },
  "rows": [                            # row = Excel row number in the export; date guards against drift
    {"row": 26, "date": "1992-06-10", "role": "pic"},
    {"row": 2303, "date": "2009-05-06", "delete": true},
    {"row": 563, "date": "1998-03-28", "split": [{"role": "pic", "set": {...}}, {"role": "dual", "set": {...}}]},
    {"row": 1176, "date": "2002-07-17", "role": "dual", "set": {"name_instructor": "..."}}
  ]
}

"set" values use the app's field names, with durations in decimal hours.
"""
import json

import openpyxl

from . import flights
from .fields import CUSTOM_NUMBERS, DURATIONS, ROLES, hours_to_minutes

# FLYLOG column -> app field
COLUMN_MAP = {
    "DATE": "date", "DEPARTURE_AIRPORT": "dep", "ARRIVAL_AIRPORT": "arr", "ROUTE": "route",
    "AIRCRAFT_TYPE": "type_code", "AIRCRAFT_REGISTRATION": "registration",
    "TIME_BLOCK_START": "off_time", "TIME_BLOCK_END": "on_time",
    "DURATION_BLOCK": "flight_time", "DURATION_SIMULATOR": "sim_time", "SIMULATOR_TYPE": "sim_device",
    "DURATION_PIC": "pic", "DURATION_PICUS": "picus", "DURATION_SIC": "sic", "DURATION_DUAL": "dual",
    "DURATION_INSTRUCTOR": "instructor", "DURATION_EXAMINER": "examiner", "DURATION_NIGHT": "night",
    "DURATION_IFR_ACTUAL": "ifr_actual", "DURATION_IFR_SIMULATED": "ifr_sim", "DURATION_XC": "xc",
    "DURATION_MULTI_PILOT": "multi_pilot",
    "LDGS_DAY": "ldg_day", "LDGS_NIGHT": "ldg_night",
    "TAKEOFFS_DAY": "to_day", "TAKEOFFS_NIGHT": "to_night",
    "APPROACH_TYPE": "approach_type", "APPROACH_NR": "approaches",
    "NAME_PIC": "name_pic", "NAME_COPILOT": "name_copilot", "NAME_STUDENT": "name_student",
    "NAME_INSTRUCTOR": "name_instructor", "NAME_EXAMINER": "name_examiner",
    "REMARKS": "remarks", "TAGS": "tags",
}
COUNT_FIELDS = {"ldg_day", "ldg_night", "to_day", "to_night", "approaches"}
DEFAULT_USER_FIELDS = {"NVG": "uh1", "SHIPS": "un1"}


def _text(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return "" if text in ("#N/A", "#VALUE!", "#REF!") else text


def _number(value):
    return float(value) if value not in (None, "") else 0.0


def read_export(path):
    """Yield (excel_row_number, {column: text}) for each data row."""
    wb = openpyxl.load_workbook(path, read_only=True)
    rows = wb.worksheets[0].iter_rows(values_only=True)
    header = [_text(h) for h in next(rows)]
    for number, values in enumerate(rows, start=2):
        record = {h: _text(v) for h, v in zip(header, values) if h}
        if any(record.values()):
            yield number, record


def map_row(raw, rules):
    """FLYLOG record -> storage-format flight (minutes), with the global rules applied."""
    row = {}
    for column, field in COLUMN_MAP.items():
        value = raw.get(column, "")
        if field in DURATIONS:
            row[field] = hours_to_minutes(value)
        elif field in COUNT_FIELDS:
            row[field] = int(_number(value))
        else:
            row[field] = value or None
    if row["off_time"] == "00:00" and not row["on_time"]:
        row["off_time"] = None                     # FLYLOG placeholder, not a real time
    if row["route"] and row["route"] == f"{row['dep']}|{row['arr']}":
        row["route"] = None                        # route only repeats from/to
    if row["approach_type"] and not row["approaches"]:
        row["approaches"] = 1

    # User fields (NVG hours, ship landings by default)
    targets = rules.get("user_fields", DEFAULT_USER_FIELDS)
    for column, slot in targets.items():
        value = _number(raw.get(column))
        if slot in CUSTOM_NUMBERS:
            row[slot] = int(value)
        elif column == "NVG" and rules.get("nvg_milliseconds"):
            # NVG: milliseconds in FLYLOG; small integers are ignored (owner decision D15)
            row[slot] = int(round(value / 60000)) if value >= rules.get("nvg_ignore_below", 1000) else 0
        else:
            row[slot] = hours_to_minutes(value)

    # Simulators
    is_sim = row["type_code"] == "SIM" or row["registration"] in rules.get("sim_registrations", []) \
        or row["sim_time"] > 0
    row["is_sim"] = 1 if is_sim else 0
    if is_sim:
        devices = rules.get("sim_devices", {})
        device = row["sim_device"] or rules.get("sim_default_device")
        if row["registration"] in rules.get("sim_registrations", []) and not row["sim_device"]:
            # e.g. AUH139 logged as an A139 aircraft: device follows the logged type
            device = next((d for d, v in devices.items() if v.get("type") == row["type_code"]), device)
        info = devices.get(device, {})
        row["sim_device"] = device
        row["sim_level"] = info.get("level")
        row["type_code"] = info.get("type", row["type_code"])
        if row["sim_level"] == "D" and rules.get("level_d_counts_as_flight_time"):
            row["flight_time"] = row["flight_time"] or row["sim_time"]
            row["sim_time"] = row["sim_time"] or row["flight_time"]
        else:
            row["sim_time"] = row["sim_time"] or row["flight_time"]
            row["flight_time"] = 0

    # IFR: total must equal actual + simulated; fill any unsplit remainder (owner decision D16)
    ifr = hours_to_minutes(raw.get("DURATION_IFR"))
    gap = ifr - row["ifr_actual"] - row["ifr_sim"]
    if rules.get("ifr_fill_split") and gap > 0:
        row["ifr_sim" if is_sim else "ifr_actual"] += gap
    return row


def _apply(row, change):
    """Apply one correction ({role, set}) to a storage-format flight."""
    row = dict(row)
    for field, value in (change.get("set") or {}).items():
        row[field] = hours_to_minutes(value) if field in DURATIONS else (value if value != "" else None)
    role = change.get("role")
    if role:
        if role not in ROLES:
            raise ValueError(f"Unknown role {role!r}")
        for r in ROLES:
            row[r] = 0
        row[role] = row["flight_time"] or row["sim_time"]
    return row


def import_export(conn, path, corrections=None, replace=False):
    """Import the export at `path`. Returns a summary dict; raises on unknown/mismatched corrections."""
    corrections = corrections or {}
    rules = corrections.get("rules", {})
    by_row = {}
    for c in corrections.get("rows", []):
        by_row.setdefault(c["row"], []).append(c)

    if replace:
        conn.execute("DELETE FROM flight WHERE source_row IS NOT NULL")
        conn.execute("DELETE FROM import_raw")

    summary = {"read": 0, "imported": 0, "deleted": 0, "split": 0, "corrected": 0, "invalid": []}
    seen = set()
    for number, raw in read_export(path):
        summary["read"] += 1
        row = map_row(raw, rules)
        actions = []
        outputs = [row]
        for c in by_row.get(number, []):
            seen.add(number)
            if c.get("date") and c["date"] != raw.get("DATE"):
                raise ValueError(f"Correction for row {number} expects date {c['date']}, found {raw.get('DATE')}")
            if c.get("delete"):
                outputs = []
                actions.append("delete")
            elif c.get("split"):
                outputs = [_apply(row, part) for part in c["split"]]
                actions.append(f"split into {len(outputs)}")
            else:
                outputs = [_apply(o, c) for o in outputs]
                actions.append("corrected")
        conn.execute("INSERT OR REPLACE INTO import_raw VALUES (?, ?, ?, ?)",
                     (number, str(path), json.dumps(raw), json.dumps(actions) if actions else None))
        if "delete" in actions:
            summary["deleted"] += 1
        elif any(a.startswith("split") for a in actions):
            summary["split"] += 1
        elif actions:
            summary["corrected"] += 1
        for i, out in enumerate(outputs):
            out["source_row"] = number + i / 10          # split parts: 563.0, 563.1
            try:
                flights.insert(conn, out, commit=False)
                summary["imported"] += 1
            except flights.ValidationError as e:
                summary["invalid"].append({"row": number, "date": raw.get("DATE"), "errors": e.errors})

    missing = sorted(set(by_row) - seen)
    if missing:
        raise ValueError(f"Corrections refer to rows not in the export: {missing}")
    if summary["invalid"]:
        conn.rollback()
    else:
        _add_places(conn)
        conn.commit()
    return summary


def _add_places(conn):
    conn.execute("""INSERT OR IGNORE INTO place (code)
                    SELECT dep FROM flight WHERE dep IS NOT NULL UNION SELECT arr FROM flight WHERE arr IS NOT NULL""")
    conn.execute("INSERT OR IGNORE INTO aircraft_type (code, category) "
                 "SELECT DISTINCT type_code, 'helicopter' FROM flight")


def load_corrections(path):
    with open(path) as f:
        return json.load(f)
