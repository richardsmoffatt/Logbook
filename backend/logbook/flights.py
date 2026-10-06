"""Flight validation and storage. The API exchanges durations as decimal hours."""
import datetime
import re

from . import custom

from .fields import COUNTS, CUSTOM_HOURS, DURATIONS, FIELD_KIND, FIELD_LABEL, FIELD_NAMES, ROLE_LABEL, ROLES, \
    hours_to_minutes, minutes_to_hours

_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
UPPER = ("dep", "arr", "type_code", "registration")


def from_api(data):
    """API dict (hours) -> storage dict (minutes). Unknown keys are ignored."""
    row = {}
    for name in FIELD_NAMES:
        if name not in data:
            continue
        value = data[name]
        kind = FIELD_KIND[name]
        if kind == "duration":
            row[name] = hours_to_minutes(value)
        elif kind == "count":
            row[name] = int(value or 0)
        elif kind == "flag":
            row[name] = 1 if value else 0
        else:
            value = (str(value).strip() if value is not None else "") or None
            if value and name in UPPER:
                value = value.upper()
            row[name] = value
    return row


def to_api(row):
    out = {"id": row["id"]}
    for name in FIELD_NAMES:
        value = row[name]
        kind = FIELD_KIND[name]
        if kind == "duration":
            value = minutes_to_hours(value)
        elif kind == "flag":
            value = bool(value)
        out[name] = value
    out["ifr"] = minutes_to_hours(row["ifr_actual"] + row["ifr_sim"])
    return out


def validate(row, labels=None):
    """Return a list of human-readable problems with a storage-format flight (empty = valid).
    labels: names of the owner's user fields, so messages use them."""
    label = {**FIELD_LABEL, **(labels or {})}
    errors = []
    try:
        datetime.date.fromisoformat(row.get("date") or "")
    except ValueError:
        errors.append("Date is required (YYYY-MM-DD).")
    if not row.get("type_code"):
        errors.append("Aircraft type is required.")
    for name in DURATIONS + COUNTS:
        if (row.get(name) or 0) < 0:
            errors.append(f"{label[name]} cannot be negative.")
    for name in ("off_time", "on_time"):
        if row.get(name) and not _TIME.match(row[name]):
            errors.append(f"{label[name]} must be HH:MM.")
    if row.get("pf_pm") not in (None, "PF", "PM"):
        errors.append("PF/PM must be PF, PM or blank.")

    flight = row.get("flight_time") or 0
    sim = row.get("sim_time") or 0
    if row.get("is_sim"):
        if not sim:
            errors.append("A simulator session needs sim time.")
    elif sim:
        errors.append("Sim time can only be logged on a simulator session.")
    if not flight and not sim:
        errors.append("Flight time (or sim time for a sim-only session) is required.")

    logged = [r for r in ROLES if row.get(r)]
    if len(logged) > 1:
        errors.append("Only one of PIC, PICUS, SIC or Dual may be logged on an entry.")
    if flight:
        if not logged:
            errors.append("Flight time needs a role (PIC, PICUS, SIC or Dual).")
        elif row[logged[0]] != flight:
            errors.append(f"{ROLE_LABEL[logged[0]]} time must equal flight time.")

    total = flight or sim
    for name in ("instructor", "examiner", "night", "xc", "multi_pilot", *CUSTOM_HOURS):
        if (row.get(name) or 0) > total:
            errors.append(f"{label[name]} cannot exceed the entry's total time.")
    if (row.get("ifr_actual") or 0) + (row.get("ifr_sim") or 0) > total:
        errors.append("IFR (actual + simulated) cannot exceed the entry's total time.")
    if row.get("approaches") and not row.get("approach_type"):
        errors.append("Give an approach type when logging approaches.")
    return errors


class ValidationError(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def _complete(row):
    """Fill defaults so validation sees every field."""
    full = {name: None for name in FIELD_NAMES}
    for name in DURATIONS + COUNTS + ["is_sim"]:
        full[name] = 0
    full.update(row)
    return full


def insert(conn, row, commit=True):
    row = _complete(row)
    errors = validate(row, custom.labels(conn))
    if errors:
        raise ValidationError(errors)
    cols = FIELD_NAMES + ["source_row"]
    cur = conn.execute(f"INSERT INTO flight ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                       [row.get(c) for c in cols])
    if commit:
        conn.commit()
    return cur.lastrowid


def update(conn, flight_id, changes):
    current = get(conn, flight_id)
    if current is None:
        return None
    row = {name: current[name] for name in FIELD_NAMES}
    row.update(changes)
    errors = validate(row, custom.labels(conn))
    if errors:
        raise ValidationError(errors)
    sets = ", ".join(f"{c} = ?" for c in FIELD_NAMES)
    conn.execute(f"UPDATE flight SET {sets}, updated_at = datetime('now') WHERE id = ?",
                 [row[c] for c in FIELD_NAMES] + [flight_id])
    conn.commit()
    return get(conn, flight_id)


def get(conn, flight_id):
    return conn.execute("SELECT * FROM flight WHERE id = ?", (flight_id,)).fetchone()


def delete(conn, flight_id):
    cur = conn.execute("DELETE FROM flight WHERE id = ?", (flight_id,))
    conn.commit()
    return cur.rowcount > 0


def search(conn, q=None, date_from=None, date_to=None, type_code=None, limit=50, offset=0):
    where, args = [], []
    if q:
        like = f"%{q}%"
        where.append("(remarks LIKE ? OR dep LIKE ? OR arr LIKE ? OR registration LIKE ? OR type_code LIKE ? "
                     "OR name_pic LIKE ? OR name_copilot LIKE ? OR name_instructor LIKE ? OR tags LIKE ?)")
        args += [like] * 9
    if date_from:
        where.append("date >= ?"); args.append(date_from)
    if date_to:
        where.append("date <= ?"); args.append(date_to)
    if type_code:
        where.append("type_code = ?"); args.append(type_code)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM flight {clause}", args).fetchone()[0]
    rows = conn.execute(f"SELECT * FROM flight {clause} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
                        args + [limit, offset]).fetchall()
    return total, rows
