"""People flown with: every name in the crew fields, with hours and a breakdown per person."""
from .fields import ROLE_SQL, minutes_to_hours

# Crew field -> the other person's role on that flight
CREW_FIELDS = {
    "name_pic": "PIC",
    "name_copilot": "Co-pilot",
    "name_instructor": "Instructor",
    "name_examiner": "Examiner",
    "name_student": "Student",
}
SELF = "SELF"
TIME = "CASE WHEN f.flight_time > 0 THEN f.flight_time ELSE f.sim_time END"

# One row per (person, flight); a person in two fields on one flight (e.g. PIC and instructor) counts once.
_LINKS = " UNION ".join(
    f"SELECT {col} AS person, id AS flight_id FROM flight WHERE {col} IS NOT NULL AND {col} != '{SELF}'"
    for col in CREW_FIELDS)
_THEIR_ROLES = " UNION ALL ".join(
    f"SELECT {col} AS person, '{label}' AS role FROM flight WHERE {col} IS NOT NULL AND {col} != '{SELF}'"
    for col, label in CREW_FIELDS.items())


def summary(conn, q=None):
    args = []
    where = ""
    if q:
        where = "WHERE l.person LIKE ?"
        args.append(f"%{q}%")
    rows = conn.execute(f"""
        SELECT l.person, COUNT(*) AS flights, SUM({TIME}) AS minutes,
               SUM(f.pic) AS pic, SUM(f.picus) AS picus, SUM(f.sic) AS sic, SUM(f.dual) AS dual,
               SUM(f.night) AS night, SUM(f.ifr_actual + f.ifr_sim) AS ifr,
               SUM(f.is_sim) AS sims, MIN(f.date) AS first, MAX(f.date) AS last,
               GROUP_CONCAT(DISTINCT f.type_code) AS types
        FROM ({_LINKS}) l JOIN flight f ON f.id = l.flight_id {where}
        GROUP BY l.person ORDER BY minutes DESC""", args).fetchall()
    roles = {}
    for person, role, n in conn.execute(f"SELECT person, role, COUNT(*) FROM ({_THEIR_ROLES}) GROUP BY 1, 2"):
        roles.setdefault(person, {})[role] = n
    out = []
    for r in rows:
        item = dict(r)
        item["hours"] = minutes_to_hours(item.pop("minutes"))
        for k in ("pic", "picus", "sic", "dual", "night", "ifr"):
            item[k] = minutes_to_hours(item[k])
        item["types"] = sorted((item["types"] or "").split(","))
        item["their_roles"] = roles.get(r["person"], {})
        out.append(item)
    return out


def detail(conn, name):
    base = f"FROM ({_LINKS}) l JOIN flight f ON f.id = l.flight_id WHERE l.person = ?"
    if not conn.execute(f"SELECT 1 {base} LIMIT 1", (name,)).fetchone():
        return None
    group = lambda expr: [
        {"key": k, "flights": n, "hours": minutes_to_hours(m)}
        for k, n, m in conn.execute(f"SELECT {expr}, COUNT(*), SUM({TIME}) {base} GROUP BY 1 ORDER BY 3 DESC", (name,))]
    their = [{"key": label, "flights": n, "hours": minutes_to_hours(m)}
             for col, label in CREW_FIELDS.items()
             for n, m in conn.execute(f"SELECT COUNT(*), SUM({TIME}) FROM flight f WHERE f.{col} = ?", (name,))
             if n]
    flights = [dict(r) for r in conn.execute(
        f"SELECT f.id, f.date, f.dep, f.arr, f.type_code, f.registration, f.is_sim, {TIME} AS minutes, "
        f"{ROLE_SQL} AS my_role, f.remarks {base} ORDER BY f.date DESC, f.id DESC", (name,))]
    for f in flights:
        f["hours"] = minutes_to_hours(f.pop("minutes"))
    return {
        "person": name,
        "flights": len(flights),
        "hours": round(sum(f["hours"] for f in flights), 1),
        "first": flights[-1]["date"],
        "last": flights[0]["date"],
        "my_role": group(ROLE_SQL),
        "their_role": sorted(their, key=lambda x: -x["hours"]),
        "by_type": group("f.type_code"),
        "by_year": sorted(group("substr(f.date, 1, 4)"), key=lambda x: x["key"]),
        "recent": flights,
    }


def rename(conn, old, new):
    """Rename (or merge into an existing name) across every crew field. Returns entries changed."""
    new = new.strip()
    if not new or new == SELF:
        raise ValueError("Give a new name.")
    changed = 0
    for col in CREW_FIELDS:
        changed += conn.execute(f"UPDATE flight SET {col} = ?, updated_at = datetime('now') WHERE {col} = ?",
                                (new, old)).rowcount
    conn.commit()
    return changed
