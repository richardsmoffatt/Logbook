import datetime
import json
import os
import pathlib
import tempfile

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import custom, db, flights, importer, people, reports
from .fields import CUSTOM_SLOTS, DIMENSIONS, FLIGHT_FIELDS, METRICS, ROLE_LABEL, minutes_to_hours

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "logbook.db"
FRONTEND = ROOT / "frontend" / "dist"


def create_app(db_path=None):
    db_path = pathlib.Path(db_path or os.environ.get("LOGBOOK_DB") or DEFAULT_DB)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(str(db_path))
    app = FastAPI(title="Logbook")
    app.state.conn = conn

    def invalid(e):
        return HTTPException(422, detail={"errors": e.errors})

    # ---- flights -------------------------------------------------------------------------
    @app.get("/api/flights")
    def list_flights(q: str = None, date_from: str = None, date_to: str = None, type_code: str = None,
                     limit: int = 50, offset: int = 0):
        total, rows = flights.search(conn, q, date_from, date_to, type_code, min(limit, 500), offset)
        return {"total": total, "items": [flights.to_api(r) for r in rows]}

    @app.get("/api/flights/last")
    def last_flight():
        row = conn.execute("SELECT * FROM flight ORDER BY date DESC, id DESC LIMIT 1").fetchone()
        return flights.to_api(row) if row else None

    @app.get("/api/flights/{flight_id}")
    def get_flight(flight_id: int):
        row = flights.get(conn, flight_id)
        if row is None:
            raise HTTPException(404, "Flight not found")
        return flights.to_api(row)

    @app.post("/api/flights", status_code=201)
    def create_flight(data: dict = Body(...)):
        try:
            new_id = flights.insert(conn, flights.from_api(data))
        except flights.ValidationError as e:
            raise invalid(e)
        return flights.to_api(flights.get(conn, new_id))

    @app.put("/api/flights/{flight_id}")
    def update_flight(flight_id: int, data: dict = Body(...)):
        try:
            row = flights.update(conn, flight_id, flights.from_api(data))
        except flights.ValidationError as e:
            raise invalid(e)
        if row is None:
            raise HTTPException(404, "Flight not found")
        return flights.to_api(row)

    @app.delete("/api/flights/{flight_id}", status_code=204)
    def delete_flight(flight_id: int):
        if not flights.delete(conn, flight_id):
            raise HTTPException(404, "Flight not found")

    # ---- reference data ------------------------------------------------------------------
    @app.get("/api/meta")
    def meta():
        labels = custom.labels(conn)
        distinct = lambda sql: [r[0] for r in conn.execute(sql) if r[0]]
        names = distinct("SELECT name_pic FROM flight UNION SELECT name_copilot FROM flight "
                         "UNION SELECT name_instructor FROM flight UNION SELECT name_student FROM flight "
                         "UNION SELECT name_examiner FROM flight")
        return {
            # User-field slots appear only when defined, under the owner's names
            "fields": [{"key": k, "label": labels.get(k, l), "kind": t} for k, l, t in FLIGHT_FIELDS
                       if k not in CUSTOM_SLOTS or k in labels],
            "metrics": [{"key": k, "label": labels.get(k, v[0]), "kind": v[1]} for k, v in METRICS.items()
                        if k not in CUSTOM_SLOTS or k in labels],
            "custom_fields": custom.active(conn),
            "dimensions": [{"key": k, "label": v[0]} for k, v in DIMENSIONS.items()],
            "roles": [{"key": k, "label": v} for k, v in ROLE_LABEL.items()],
            "types": [dict(r) for r in conn.execute("SELECT * FROM aircraft_type ORDER BY code")],
            "registrations": [dict(r) for r in conn.execute(
                "SELECT registration, type_code, MAX(is_sim) AS is_sim, COUNT(*) AS n FROM flight "
                "WHERE registration IS NOT NULL GROUP BY registration ORDER BY MAX(date) DESC")],
            "places": [dict(r) for r in conn.execute("SELECT * FROM place ORDER BY code")],
            "names": sorted(set(names) - {"SELF"}),
            "sim_devices": distinct("SELECT DISTINCT sim_device FROM flight ORDER BY 1"),
            "approach_types": distinct("SELECT DISTINCT approach_type FROM flight ORDER BY 1"),
        }

    @app.put("/api/types/{code}")
    def save_type(code: str, data: dict = Body(...)):
        code = code.upper()
        try:
            conn.execute("INSERT INTO aircraft_type (code, name, category, engines, power, multi_pilot) "
                         "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(code) DO UPDATE SET name = excluded.name, "
                         "category = excluded.category, engines = excluded.engines, power = excluded.power, "
                         "multi_pilot = excluded.multi_pilot",
                         (code, data.get("name"), data.get("category") or "helicopter", data.get("engines") or None,
                          data.get("power") or None, 1 if data.get("multi_pilot") else 0))
        except Exception as e:  # CHECK constraint
            raise HTTPException(422, detail={"errors": [str(e)]})
        conn.commit()
        return dict(conn.execute("SELECT * FROM aircraft_type WHERE code = ?", (code,)).fetchone())

    @app.get("/api/places")
    def list_places():
        return [dict(r) for r in conn.execute(
            "SELECT p.*, (SELECT COUNT(*) FROM flight f WHERE f.dep = p.code OR f.arr = p.code) AS flights, "
            "(SELECT MAX(date) FROM flight f WHERE f.dep = p.code OR f.arr = p.code) AS last_visit "
            "FROM place p ORDER BY flights DESC")]

    @app.put("/api/places/{code}")
    def save_place(code: str, data: dict = Body(...)):
        code = code.upper()
        lat, lon = data.get("lat"), data.get("lon")
        try:
            lat = float(lat) if lat not in (None, "") else None
            lon = float(lon) if lon not in (None, "") else None
        except ValueError:
            raise HTTPException(422, detail={"errors": ["Latitude/longitude must be numbers."]})
        if (lat is not None and not -90 <= lat <= 90) or (lon is not None and not -180 <= lon <= 180):
            raise HTTPException(422, detail={"errors": ["Latitude/longitude out of range."]})
        conn.execute("INSERT INTO place (code, name, kind, lat, lon, notes) VALUES (?, ?, ?, ?, ?, ?) "
                     "ON CONFLICT(code) DO UPDATE SET name = excluded.name, kind = excluded.kind, "
                     "lat = excluded.lat, lon = excluded.lon, notes = excluded.notes",
                     (code, data.get("name") or None, data.get("kind") or None, lat, lon, data.get("notes") or None))
        conn.commit()
        return dict(conn.execute("SELECT * FROM place WHERE code = ?", (code,)).fetchone())

    # ---- user-defined fields -------------------------------------------------------------
    def custom_call(fn, *args):
        try:
            return fn(conn, *args)
        except custom.CustomFieldError as e:
            raise HTTPException(422, detail={"errors": [str(e)]})

    @app.get("/api/custom-fields")
    def list_custom():
        return custom.listing(conn)

    @app.post("/api/custom-fields", status_code=201)
    def add_custom(data: dict = Body(...)):
        return custom_call(custom.add, data.get("label"), data.get("kind"))

    @app.put("/api/custom-fields/{slot}")
    def rename_custom(slot: str, data: dict = Body(...)):
        return custom_call(custom.rename, slot, data.get("label"))

    @app.delete("/api/custom-fields/{slot}")
    def delete_custom(slot: str):
        return {"cleared": custom_call(custom.remove, slot)}

    # ---- people --------------------------------------------------------------------------
    @app.get("/api/people")
    def list_people(q: str = None):
        return people.summary(conn, q)

    @app.get("/api/people/detail")
    def person_detail(name: str):
        result = people.detail(conn, name)
        if result is None:
            raise HTTPException(404, "No flights with that person")
        return result

    @app.post("/api/people/rename")
    def rename_person(data: dict = Body(...)):
        try:
            return {"changed": people.rename(conn, data.get("from") or "", data.get("to") or "")}
        except ValueError as e:
            raise HTTPException(422, detail={"errors": [str(e)]})

    # ---- dashboard -----------------------------------------------------------------------
    @app.get("/api/summary")
    def summary(today: str = None):
        day = datetime.date.fromisoformat(today) if today else datetime.date.today()
        since = lambda days: (day - datetime.timedelta(days=days)).isoformat()
        q = lambda sql, *a: conn.execute(sql, a).fetchone()
        tot = q("SELECT COUNT(*), SUM(flight_time), SUM(sim_time), SUM(pic), SUM(picus), SUM(sic), SUM(dual), "
                "SUM(instructor), SUM(night), SUM(ifr_actual + ifr_sim), MIN(date), MAX(date) FROM flight")
        keys = ["flight_time", "sim_time", "pic", "picus", "sic", "dual", "instructor", "night", "ifr"]
        totals = {k: minutes_to_hours(v) for k, v in zip(keys, tot[1:10])}
        periods = []
        for label, start in (("Last 28 days", since(28)), ("Last 90 days", since(90)),
                             ("Last 12 months", since(365)), (f"{day.year} to date", f"{day.year}-01-01")):
            r = q("SELECT SUM(flight_time) FROM flight WHERE date > ? AND date <= ?", start, day.isoformat())
            periods.append({"label": label, "hours": minutes_to_hours(r[0])})
        # Last 90 days: landings, approaches and every user field (hours or number)
        rows = [("ldg_day", "Day landings", "number"), ("ldg_night", "Night landings", "number"),
                ("approaches", "Instrument approaches", "number")]
        rows += [(f["slot"], f["label"] + (" hours" if f["kind"] == "hours" and "hour" not in f["label"].lower() else ""),
                  f["kind"]) for f in custom.active(conn)]
        cur = q(f"SELECT {', '.join(f'SUM({c})' for c, _, _ in rows)} FROM flight WHERE date > ? AND date <= ?",
                since(90), day.isoformat())
        last = lambda col: q(f"SELECT MAX(date) FROM flight WHERE {col} > 0")[0]
        currency = [{"label": label, "kind": kind,
                     "last_90": minutes_to_hours(v) if kind == "hours" else (v or 0), "last": last(col)}
                    for (col, label, kind), v in zip(rows, cur)]
        by_type = [dict(type_code=r[0], hours=minutes_to_hours(r[1]), last=r[2]) for r in conn.execute(
            "SELECT type_code, SUM(flight_time), MAX(date) FROM flight GROUP BY type_code "
            "HAVING SUM(flight_time) > 0 ORDER BY 2 DESC")]
        return {"entries": tot[0], "first": tot[10], "last": tot[11], "totals": totals,
                "periods": periods, "currency": currency, "by_type": by_type, "as_of": day.isoformat()}

    # ---- reports -------------------------------------------------------------------------
    @app.post("/api/reports/run")
    def run_report(spec: dict = Body(...)):
        try:
            return reports.run(conn, spec)
        except reports.ReportError as e:
            raise HTTPException(422, detail={"errors": [str(e)]})

    @app.post("/api/reports/export")
    def export_report(spec: dict = Body(...), format: str = "csv"):
        try:
            result = reports.run(conn, spec)
        except reports.ReportError as e:
            raise HTTPException(422, detail={"errors": [str(e)]})
        name = (spec.get("title") or "logbook-report").replace("/", "-")
        if format == "xlsx":
            return Response(reports.to_xlsx(result, spec.get("title") or "Logbook report"),
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
        return Response(reports.to_csv(result), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})

    @app.get("/api/reports/saved")
    def saved_reports():
        return [{"id": r["id"], "name": r["name"], "spec": json.loads(r["spec"])}
                for r in conn.execute("SELECT * FROM saved_report ORDER BY name")]

    @app.post("/api/reports/saved", status_code=201)
    def save_report(data: dict = Body(...)):
        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(422, detail={"errors": ["Give the report a name."]})
        conn.execute("INSERT INTO saved_report (name, spec) VALUES (?, ?) "
                     "ON CONFLICT(name) DO UPDATE SET spec = excluded.spec", (name, json.dumps(data.get("spec") or {})))
        conn.commit()
        return {"name": name}

    @app.delete("/api/reports/saved/{report_id}", status_code=204)
    def delete_saved(report_id: int):
        conn.execute("DELETE FROM saved_report WHERE id = ?", (report_id,))
        conn.commit()

    # ---- import & backup -----------------------------------------------------------------
    @app.post("/api/import")
    async def import_file(export: UploadFile = File(...), corrections: UploadFile = File(None),
                          replace: bool = Form(False)):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "export.xlsx"
            path.write_bytes(await export.read())
            fixes = json.loads(await corrections.read()) if corrections else None
            if not replace and conn.execute("SELECT COUNT(*) FROM flight WHERE source_row IS NOT NULL").fetchone()[0]:
                raise HTTPException(409, detail={"errors": ["A logbook has already been imported. "
                                                            "Tick 'replace' to re-import it."]})
            try:
                return importer.import_export(conn, path, fixes, replace=replace)
            except ValueError as e:
                conn.rollback()
                raise HTTPException(422, detail={"errors": [str(e)]})

    @app.get("/api/backup")
    def backup():
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "backup.db"
            dest = db.sqlite3.connect(target)
            conn.backup(dest)
            dest.close()
            data = target.read_bytes()
        return Response(data, media_type="application/x-sqlite3",
                        headers={"Content-Disposition": f'attachment; filename="logbook-{stamp}.db"'})

    # ---- frontend ------------------------------------------------------------------------
    if FRONTEND.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "Not found")
            return FileResponse(FRONTEND / "index.html")

    return app
