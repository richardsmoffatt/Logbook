"""User-defined fields: up to five hours fields (uh1-uh5) and five number fields (un1-un5)."""
from .fields import CUSTOM_HOURS, CUSTOM_NUMBERS, MAX_CUSTOM, minutes_to_hours

KINDS = {"hours": CUSTOM_HOURS, "number": CUSTOM_NUMBERS}


class CustomFieldError(ValueError):
    pass


def kind_of(slot):
    return "hours" if slot in CUSTOM_HOURS else "number"


def active(conn):
    """Defined fields in display order: [{slot, label, kind}]."""
    return [{"slot": r["slot"], "label": r["label"], "kind": kind_of(r["slot"])}
            for r in conn.execute("SELECT * FROM custom_field ORDER BY position, slot")]


def labels(conn):
    return {f["slot"]: f["label"] for f in active(conn)}


def listing(conn):
    """Active fields with usage, for the Manage fields dialog."""
    out = []
    for f in active(conn):
        n, total = conn.execute(f"SELECT COUNT(*), COALESCE(SUM({f['slot']}), 0) FROM flight "
                                f"WHERE {f['slot']} > 0").fetchone()
        f["entries"] = n
        f["total"] = minutes_to_hours(total) if f["kind"] == "hours" else total
        out.append(f)
    return out


def _clean_label(conn, label, slot=None):
    label = (label or "").strip()
    if not label:
        raise CustomFieldError("Give the field a name.")
    if len(label) > 30:
        raise CustomFieldError("Keep the name to 30 characters or fewer.")
    clash = conn.execute("SELECT slot FROM custom_field WHERE lower(label) = lower(?) AND slot != ?",
                         (label, slot or "")).fetchone()
    if clash:
        raise CustomFieldError(f"There is already a field called {label!r}.")
    return label


def add(conn, label, kind):
    if kind not in KINDS:
        raise CustomFieldError("Field type must be hours or number.")
    label = _clean_label(conn, label)
    used = {r[0] for r in conn.execute("SELECT slot FROM custom_field")}
    free = [s for s in KINDS[kind] if s not in used]
    if not free:
        raise CustomFieldError(f"You already have {MAX_CUSTOM} {kind} fields; remove one first.")
    slot = free[0]
    # A freed slot is always emptied on removal, but clear it again in case of old data.
    conn.execute(f"UPDATE flight SET {slot} = 0 WHERE {slot} != 0")
    position = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM custom_field").fetchone()[0]
    conn.execute("INSERT INTO custom_field (slot, label, position) VALUES (?, ?, ?)", (slot, label, position))
    conn.commit()
    return {"slot": slot, "label": label, "kind": kind}


def _check(conn, slot):
    if slot not in CUSTOM_HOURS + CUSTOM_NUMBERS or \
            not conn.execute("SELECT 1 FROM custom_field WHERE slot = ?", (slot,)).fetchone():
        raise CustomFieldError("No such field.")


def rename(conn, slot, label):
    _check(conn, slot)
    label = _clean_label(conn, label, slot)
    conn.execute("UPDATE custom_field SET label = ? WHERE slot = ?", (label, slot))
    conn.commit()
    return {"slot": slot, "label": label, "kind": kind_of(slot)}


def remove(conn, slot):
    """Delete the field and the values logged in it. Returns how many entries had a value."""
    _check(conn, slot)
    cleared = conn.execute(f"UPDATE flight SET {slot} = 0 WHERE {slot} != 0").rowcount
    conn.execute("DELETE FROM custom_field WHERE slot = ?", (slot,))
    conn.commit()
    return cleared
