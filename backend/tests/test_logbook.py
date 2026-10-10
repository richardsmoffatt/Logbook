"""Tests use a small synthetic FLYLOG export - never real logbook data (the repository is public)."""
import json

import openpyxl
import pytest
from fastapi.testclient import TestClient

from logbook import api, db, importer

HEADER = ["DATE", "DEPARTURE_AIRPORT", "ARRIVAL_AIRPORT", "AIRCRAFT_TYPE", "AIRCRAFT_REGISTRATION",
          "DURATION_BLOCK", "LDGS_DAY", "LDGS_NIGHT", "TIME_BLOCK_START", "DURATION_PIC", "DURATION_PICUS",
          "DURATION_SIC", "DURATION_DUAL", "DURATION_INSTRUCTOR", "DURATION_NIGHT", "DURATION_IFR",
          "DURATION_IFR_ACTUAL", "DURATION_IFR_SIMULATED", "DURATION_SIMULATOR", "SIMULATOR_TYPE", "REMARKS",
          "NAME_PIC", "NAME_INSTRUCTOR", "ROUTE", "NVG", "SHIPS"]


def row(**kw):
    base = {h: "" for h in HEADER}
    base.update({"TIME_BLOCK_START": "00:00"})
    base.update(kw)
    return [base[h] for h in HEADER]


ROWS = [
    # 2: plain PIC flight with night, NVG in ms and ship landings, partial IFR split
    row(DATE="2020-01-10", DEPARTURE_AIRPORT="OMNK", ARRIVAL_AIRPORT="RIG1", AIRCRAFT_TYPE="A139",
        AIRCRAFT_REGISTRATION="LIW01", DURATION_BLOCK="2.0", LDGS_DAY="2", LDGS_NIGHT="1", DURATION_PIC="2.0",
        DURATION_NIGHT="1.0", DURATION_IFR="1.0", DURATION_IFR_ACTUAL="0.4", NVG="3600000", SHIPS="3",
        NAME_PIC="SELF", ROUTE="OMNK|RIG1"),
    # 3: two roles - fixed by correction to PIC
    row(DATE="2020-01-11", DEPARTURE_AIRPORT="OMNK", ARRIVAL_AIRPORT="OMNK", AIRCRAFT_TYPE="R22",
        AIRCRAFT_REGISTRATION="N-1", DURATION_BLOCK="1.0", DURATION_PIC="1.0", DURATION_DUAL="1.0", NVG="3"),
    # 4 and 5: duplicate pair - second deleted
    row(DATE="2020-01-12", DEPARTURE_AIRPORT="OMNK", ARRIVAL_AIRPORT="OMNK", AIRCRAFT_TYPE="R22",
        AIRCRAFT_REGISTRATION="N-1", DURATION_BLOCK="0.5", DURATION_SIC="0.5"),
    row(DATE="2020-01-12", DEPARTURE_AIRPORT="OMNK", ARRIVAL_AIRPORT="OMNK", AIRCRAFT_TYPE="R22",
        AIRCRAFT_REGISTRATION="N-1", DURATION_BLOCK="0.5", DURATION_SIC="0.5"),
    # 6: Level D sim with sim time only -> credited as flight time; unsplit IFR -> simulated
    row(DATE="2020-02-01", DEPARTURE_AIRPORT="OMAD", ARRIVAL_AIRPORT="OMAD", AIRCRAFT_TYPE="SIM",
        AIRCRAFT_REGISTRATION="AW139", DURATION_SIMULATOR="4.0", DURATION_PICUS="4.0", DURATION_IFR="2.0",
        SIMULATOR_TYPE="AW-139"),
    # 7: generic trainer -> sim time only, no flight time
    row(DATE="2020-02-02", DEPARTURE_AIRPORT="YSBK", ARRIVAL_AIRPORT="YSBK", AIRCRAFT_TYPE="SIM",
        AIRCRAFT_REGISTRATION="ATC810", DURATION_BLOCK="1.5", DURATION_DUAL="1.5", SIMULATOR_TYPE="Generic"),
    # 8: sim logged as an aircraft (registration rule)
    row(DATE="2020-02-03", DEPARTURE_AIRPORT="KLGA", ARRIVAL_AIRPORT="KEWR", AIRCRAFT_TYPE="A139",
        AIRCRAFT_REGISTRATION="AUH139", DURATION_BLOCK="2.0", DURATION_SIC="2.0"),
    # 9: split into two entries
    row(DATE="2020-03-01", DEPARTURE_AIRPORT="YSBK", ARRIVAL_AIRPORT="YSBK", AIRCRAFT_TYPE="B06",
        AIRCRAFT_REGISTRATION="VH-AAA", DURATION_BLOCK="3.0", LDGS_DAY="4", DURATION_PIC="3.0",
        DURATION_DUAL="0.2", REMARKS="Check & Joyflights", NAME_PIC="Instructor A", NAME_INSTRUCTOR="Instructor A"),
]

CORRECTIONS = {
    "rules": {
        "nvg_milliseconds": True, "nvg_ignore_below": 1000, "sim_registrations": ["AUH139"],
        "sim_devices": {"AW-139": {"type": "A139", "level": "D"}, "Generic": {"type": "SIM"}},
        "sim_default_device": "Generic", "level_d_counts_as_flight_time": True, "ifr_fill_split": True,
    },
    "rows": [
        {"row": 3, "date": "2020-01-11", "role": "pic"},
        {"row": 5, "date": "2020-01-12", "delete": True},
        {"row": 9, "date": "2020-03-01", "split": [
            {"role": "pic", "set": {"flight_time": 2.8, "remarks": "Joyflights", "name_pic": "SELF",
                                    "name_instructor": ""}},
            {"role": "dual", "set": {"flight_time": 0.2, "ldg_day": 0, "remarks": "Check"}}]},
    ],
}


@pytest.fixture
def export(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADER)
    for r in ROWS:
        ws.append(r)
    path = tmp_path / "export.xlsx"
    wb.save(path)
    return path


@pytest.fixture
def conn(tmp_path, export):
    c = db.connect(str(tmp_path / "test.db"))
    result = importer.import_export(c, export, CORRECTIONS)
    assert result["invalid"] == []
    return c


def total(conn, col, where="1"):
    return conn.execute(f"SELECT COALESCE(SUM({col}), 0) FROM flight WHERE {where}").fetchone()[0] / 60


def test_import_counts(conn):
    assert conn.execute("SELECT COUNT(*) FROM flight").fetchone()[0] == 8
    assert conn.execute("SELECT COUNT(*) FROM import_raw").fetchone()[0] == 8   # every source row kept


def test_flight_and_sim_rules(conn):
    # 2.0 + 1.0 + 0.5 + 4.0 (level D) + 2.0 (AUH139) + 2.8 + 0.2; generic trainer excluded
    assert total(conn, "flight_time") == pytest.approx(12.5)
    assert total(conn, "sim_time") == pytest.approx(4.0 + 1.5 + 2.0)
    sim = conn.execute("SELECT type_code, sim_level, flight_time FROM flight WHERE registration = 'AUH139'").fetchone()
    assert tuple(sim) == ("A139", "D", 120)
    generic = conn.execute("SELECT is_sim, type_code, flight_time, sim_time FROM flight WHERE registration = 'ATC810'").fetchone()
    assert tuple(generic) == (1, "SIM", 0, 90)


def test_roles_nvg_ifr_ships(conn):
    assert total(conn, "pic") == pytest.approx(2.0 + 1.0 + 2.8)
    assert total(conn, "dual") == pytest.approx(0.2 + 1.5)          # split check + generic trainer
    assert total(conn, "uh1") == pytest.approx(1.0)                  # NVG user field; small value is not NVG
    assert total(conn, "un1") * 60 == 3 + 3                           # ship landings, incl. the small NVG value
    assert total(conn, "ifr_actual") == pytest.approx(1.0)           # 0.4 + unsplit 0.6
    assert total(conn, "ifr_sim") == pytest.approx(2.0)
    split = conn.execute("SELECT flight_time, ldg_day, name_instructor FROM flight WHERE date = '2020-03-01' "
                         "ORDER BY source_row").fetchall()
    assert [tuple(r) for r in split] == [(168, 4, None), (12, 0, "Instructor A")]


def test_placeholder_time_and_route(conn):
    r = conn.execute("SELECT off_time, route FROM flight WHERE date = '2020-01-10'").fetchone()
    assert tuple(r) == (None, None)


def test_correction_date_guard(tmp_path, export):
    c = db.connect(str(tmp_path / "guard.db"))
    bad = dict(CORRECTIONS, rows=[{"row": 3, "date": "1999-01-01", "role": "pic"}])
    with pytest.raises(ValueError, match="expects date"):
        importer.import_export(c, export, bad)


def test_invalid_without_corrections_rolls_back(tmp_path, export):
    c = db.connect(str(tmp_path / "raw.db"))
    result = importer.import_export(c, export, {"rules": CORRECTIONS["rules"]})
    assert {p["row"] for p in result["invalid"]} == {3, 9}            # two roles on one entry
    assert c.execute("SELECT COUNT(*) FROM flight").fetchone()[0] == 0


@pytest.fixture
def client(tmp_path, export):
    app = api.create_app(tmp_path / "api.db")
    importer.import_export(app.state.conn, export, CORRECTIONS)
    return TestClient(app)


NEW = {"date": "2026-10-06", "dep": "omnk", "arr": "OMNK", "type_code": "A139", "registration": "LIW18",
       "flight_time": 1.4, "pic": 1.4, "night": 0.5, "ifr_actual": 0.3, "ldg_day": 2, "un1": 1,
       "pf_pm": "PM", "name_pic": "SELF", "remarks": "Test"}


def test_flight_crud(client):
    r = client.post("/api/flights", json=NEW)
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["dep"] == "OMNK" and f["flight_time"] == 1.4 and f["ifr"] == 0.3
    r = client.put(f"/api/flights/{f['id']}", json={**NEW, "flight_time": 1.5, "pic": 1.5})
    assert r.json()["flight_time"] == 1.5
    assert client.get("/api/flights", params={"q": "Test"}).json()["total"] == 1
    assert client.delete(f"/api/flights/{f['id']}").status_code == 204
    assert client.get(f"/api/flights/{f['id']}").status_code == 404


@pytest.mark.parametrize("changes, message", [
    ({"sic": 1.4}, "Only one of"),
    ({"pic": 1.0}, "must equal flight time"),
    ({"pic": 0}, "needs a role"),
    ({"night": 2.0}, "Night cannot exceed"),
    ({"ifr_actual": 1.0, "ifr_sim": 1.0}, "IFR"),
    ({"pf_pm": "XX"}, "PF/PM"),
    ({"date": ""}, "Date is required"),
    ({"sim_time": 1.0}, "simulator session"),
])
def test_flight_validation(client, changes, message):
    r = client.post("/api/flights", json={**NEW, **changes})
    assert r.status_code == 422
    assert any(message in e for e in r.json()["detail"]["errors"])


def test_report_summary_grouped(client):
    spec = {"filters": {"date_from": "2020-01-01", "date_to": "2020-12-31"}, "group_by": ["type_code"],
            "columns": ["count", "flight_time", "sim_time", "un1"]}
    res = client.post("/api/reports/run", json=spec).json()
    rows = {r[0]: r[1:] for r in res["rows"]}
    assert rows["A139"] == [3, 8.0, 6.0, 3]
    assert res["totals"] == ["Total", 8, 12.5, 7.5, 6]          # R22 row adds 3 ship landings from NVG


def test_report_filters_and_roles(client):
    spec = {"filters": {"kind": "aircraft", "roles": ["pic"]}, "group_by": ["year", "role"], "columns": ["flight_time"]}
    res = client.post("/api/reports/run", json=spec).json()
    assert res["rows"] == [["2020", "PIC", 5.8]]


def test_report_detail_and_exports(client):
    spec = {"mode": "detail", "filters": {"type_codes": ["B06"]}, "columns": ["date", "remarks", "flight_time", "ldg_day"]}
    res = client.post("/api/reports/run", json=spec).json()
    assert res["rows"] == [["2020-03-01", "Joyflights", 2.8, 4], ["2020-03-01", "Check", 0.2, 0]]
    assert res["totals"] == ["2 entries", None, 3.0, 4]
    csv = client.post("/api/reports/export?format=csv", json=spec)
    assert csv.text.splitlines()[0] == "Date,Remarks,Flight time,Landings day"
    xlsx = client.post("/api/reports/export?format=xlsx", json=spec)
    assert xlsx.content[:2] == b"PK"


def test_report_rejects_unknown_names(client):
    r = client.post("/api/reports/run", json={"group_by": ["f.date; DROP TABLE flight"], "columns": ["count"]})
    assert r.status_code == 422


def test_saved_reports(client):
    spec = {"group_by": ["year"], "columns": ["flight_time"]}
    assert client.post("/api/reports/saved", json={"name": "By year", "spec": spec}).status_code == 201
    saved = client.get("/api/reports/saved").json()
    assert saved[0]["name"] == "By year" and saved[0]["spec"] == spec


def test_summary_and_meta(client):
    s = client.get("/api/summary", params={"today": "2020-03-15"}).json()
    assert s["totals"]["flight_time"] == 12.5
    assert s["periods"][1] == {"label": "Last 90 days", "hours": 12.5}
    cur = {c["label"]: c["last_90"] for c in s["currency"]}
    assert cur["Ship landings"] == 6 and cur["NVG hours"] == 1.0      # user fields appear automatically
    total_col = {c["label"]: c["total"] for c in s["currency"]}
    assert total_col["Ship landings"] == 6 and total_col["Day landings"] == 6
    meta = client.get("/api/meta").json()
    assert "Instructor A" in meta["names"] and "SELF" not in meta["names"]
    assert {p["code"] for p in meta["places"]} >= {"OMNK", "RIG1"}


def test_places_and_types(client):
    r = client.put("/api/places/rig1", json={"name": "Rig One", "kind": "rig", "lat": 24.5, "lon": 54.1})
    assert r.json()["lat"] == 24.5
    assert client.put("/api/places/RIG1", json={"lat": 120}).status_code == 422
    r = client.put("/api/types/EC35", json={"name": "H135", "engines": "multi", "power": "turbine"})
    assert r.json()["category"] == "helicopter"
    assert client.put("/api/types/X", json={"category": "balloon"}).status_code == 422


def test_import_endpoint_refuses_second_import(client, export):
    files = {"export": ("e.xlsx", export.read_bytes())}
    assert client.post("/api/import", files=files).status_code == 409
    files["corrections"] = ("c.json", json.dumps(CORRECTIONS))
    r = client.post("/api/import", files=files, data={"replace": "true"})
    assert r.status_code == 200 and r.json()["imported"] == 8


def test_backup(client):
    r = client.get("/api/backup")
    assert r.status_code == 200 and r.content.startswith(b"SQLite format 3")


def test_people_summary_and_detail(client):
    people = {p["person"]: p for p in client.get("/api/people").json()}
    assert "SELF" not in people
    a = people["Instructor A"]
    # PIC and instructor on the same 0.2 check flight counts once
    assert a["flights"] == 1 and a["hours"] == 0.2 and a["dual"] == 0.2
    assert a["their_roles"] == {"PIC": 1, "Instructor": 1}
    d = client.get("/api/people/detail", params={"name": "Instructor A"}).json()
    assert d["my_role"] == [{"key": "Dual", "flights": 1, "hours": 0.2}]
    assert {r["key"] for r in d["their_role"]} == {"PIC", "Instructor"}
    assert d["recent"][0]["remarks"] == "Check" and d["first"] == d["last"] == "2020-03-01"
    assert client.get("/api/people/detail", params={"name": "Nobody"}).status_code == 404


def test_people_rename_merges(client):
    client.post("/api/flights", json={**NEW, "name_copilot": "Instr A"})
    r = client.post("/api/people/rename", json={"from": "Instr A", "to": "Instructor A"})
    assert r.json() == {"changed": 1}
    a = {p["person"]: p for p in client.get("/api/people").json()}["Instructor A"]
    assert a["flights"] == 2 and a["their_roles"]["Co-pilot"] == 1
    assert client.post("/api/people/rename", json={"from": "Instructor A", "to": " "}).status_code == 422


def test_report_uses_user_field_names(client):
    res = client.post("/api/reports/run", json={"group_by": ["type_code"], "columns": ["uh1", "un1"],
                                                "filters": {"conditions": ["un1"]}}).json()
    assert [h["label"] for h in res["headers"]] == ["Type", "NVG", "Ship landings"]
    assert res["rows"] == [["A139", 1.0, 3], ["R22", 0.0, 3]]


def test_custom_fields_add_rename_remove(client):
    listing = client.get("/api/custom-fields").json()
    assert [(f["slot"], f["label"], f["kind"], f["total"]) for f in listing] == \
        [("uh1", "NVG", "hours", 1.0), ("un1", "Ship landings", "number", 6)]
    r = client.post("/api/custom-fields", json={"label": "Hoist cycles", "kind": "number"})
    assert r.status_code == 201 and r.json()["slot"] == "un2"
    assert client.post("/api/custom-fields", json={"label": "nvg", "kind": "hours"}).status_code == 422  # duplicate
    # New field is usable on an entry, validated under its own name, and reported
    assert client.post("/api/flights", json={**NEW, "un2": 4}).status_code == 201
    r = client.post("/api/flights", json={**NEW, "uh1": 9.0})
    assert "NVG cannot exceed the entry's total time." in r.json()["detail"]["errors"]
    meta = client.get("/api/meta").json()
    assert {"key": "un2", "label": "Hoist cycles", "kind": "count"} in meta["metrics"]
    assert not any(m["key"] == "un3" for m in meta["metrics"])        # unused slots stay hidden
    assert client.put("/api/custom-fields/un2", json={"label": "Hoist lifts"}).json()["label"] == "Hoist lifts"
    assert client.delete("/api/custom-fields/un2").json() == {"cleared": 1}
    assert client.delete("/api/custom-fields/flight_time").status_code == 422   # only user slots


def test_custom_fields_limit_of_five(client):
    for i in range(2, 6):
        assert client.post("/api/custom-fields", json={"label": f"H{i}", "kind": "hours"}).status_code == 201
    r = client.post("/api/custom-fields", json={"label": "H6", "kind": "hours"})
    assert r.status_code == 422 and "5 hours fields" in r.json()["detail"]["errors"][0]
    assert client.post("/api/custom-fields", json={"label": "N2", "kind": "number"}).status_code == 201


def test_migration_moves_nvg_and_ships(tmp_path):
    """A database from before user fields keeps its NVG and ship landings, with a backup made first."""
    import sqlite3
    # A v0 database: today's schema with the old NVG/ship columns instead of the user slots
    path2 = tmp_path / "v0.db"
    schema = db.SCHEMA
    for slot in ["uh1", "uh2", "uh3", "uh4", "uh5", "un1", "un2", "un3", "un4", "un5"]:
        schema = schema.replace(f"    {slot} INTEGER NOT NULL DEFAULT 0,\n", "")
    schema = schema.replace("approach_type TEXT,", "nvg INTEGER NOT NULL DEFAULT 0, ldg_ship INTEGER NOT NULL DEFAULT 0, approach_type TEXT,")
    v0 = sqlite3.connect(path2)
    v0.executescript(schema.replace("CREATE TABLE IF NOT EXISTS custom_field", "CREATE TABLE IF NOT EXISTS unused_v0"))
    v0.execute("DROP TABLE unused_v0")
    v0.execute("INSERT INTO flight (date, type_code, flight_time, pic, nvg, ldg_ship) VALUES ('2020-01-01', 'A139', 60, 60, 30, 2)")
    v0.commit(); v0.close()
    conn = db.connect(str(path2))
    row = conn.execute("SELECT uh1, un1 FROM flight").fetchone()
    assert tuple(row) == (30, 2)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(flight)")}
    assert "nvg" not in cols and "ldg_ship" not in cols
    assert [tuple(r) for r in conn.execute("SELECT slot, label FROM custom_field")] == [("uh1", "NVG"), ("un1", "Ship landings")]
    assert list(tmp_path.glob("v0.db.before-user-fields-*"))           # backup copy kept
    db.connect(str(path2))                                              # second open is a no-op
    assert tuple(conn.execute("SELECT uh1, un1 FROM flight").fetchone()) == (30, 2)


def test_migration_v2_moves_small_nvg_into_ship_landings(tmp_path, export):
    """A database imported before this fix (small NVG values dropped) is corrected once, from import_raw."""
    path = tmp_path / "v1.db"
    c = db.connect(str(path))
    importer.import_export(c, export, CORRECTIONS)
    # Simulate the old import: small NVG value not counted, schema at version 1
    c.execute("UPDATE flight SET un1 = 0 WHERE source_row = 3")
    c.execute("PRAGMA user_version = 1"); c.commit(); c.close()
    c = db.connect(str(path))
    assert c.execute("SELECT un1 FROM flight WHERE source_row = 3").fetchone()[0] == 3
    assert c.execute("SELECT SUM(un1) FROM flight").fetchone()[0] == 6
    assert list(tmp_path.glob("v1.db.before-ship-landings-fix-*"))     # backup kept
    c.close()
    c = db.connect(str(path))                                          # runs once only
    assert c.execute("SELECT SUM(un1) FROM flight").fetchone()[0] == 6


def test_sic_entries_name_self_as_copilot(conn):
    rows = conn.execute("SELECT name_pic, name_copilot FROM flight WHERE sic > 0").fetchall()
    assert rows and all(r["name_copilot"] == "SELF" for r in rows)


def test_sic_with_self_as_pic_is_rejected(client):
    sic = {**NEW, "pic": 0, "sic": 1.4, "name_pic": "SELF", "name_copilot": None}
    r = client.post("/api/flights", json=sic)
    assert r.status_code == 422 and any("SIC entry" in e for e in r.json()["detail"]["errors"])
    r = client.post("/api/flights", json={**sic, "name_pic": "Capt A", "name_copilot": "SELF"})
    assert r.status_code == 201


def test_migration_v3_fills_sic_copilot(tmp_path, export):
    path = tmp_path / "v2.db"
    c = db.connect(str(path))
    importer.import_export(c, export, CORRECTIONS)
    c.execute("UPDATE flight SET name_copilot = NULL WHERE sic > 0")                  # as imported before
    c.execute("UPDATE flight SET name_copilot = 'Someone' WHERE id = (SELECT MIN(id) FROM flight WHERE sic > 0)")
    c.execute("PRAGMA user_version = 2"); c.commit(); c.close()
    c = db.connect(str(path))
    names = [r[0] for r in c.execute("SELECT name_copilot FROM flight WHERE sic > 0 ORDER BY id")]
    assert names[0] == "Someone" and set(names[1:]) == {"SELF"}                        # only blanks filled
    assert list(tmp_path.glob("v2.db.before-sic-copilot-self-*"))
