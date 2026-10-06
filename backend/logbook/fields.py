"""Single source of truth for flight fields, report metrics and report dimensions.

Durations are stored as integer minutes and exchanged with the UI as decimal hours.
"""

# (column, label, kind) - kind: date | text | duration | count | choice | flag
FLIGHT_FIELDS = [
    ("date", "Date", "date"),
    ("dep", "From", "text"),
    ("arr", "To", "text"),
    ("route", "Route", "text"),
    ("type_code", "Type", "text"),
    ("registration", "Registration", "text"),
    ("is_sim", "Simulator", "flag"),
    ("sim_device", "Sim device", "text"),
    ("sim_level", "Sim level", "text"),
    ("off_time", "Off block", "text"),
    ("on_time", "On block", "text"),
    ("flight_time", "Flight time", "duration"),
    ("sim_time", "Sim time", "duration"),
    ("pic", "PIC", "duration"),
    ("picus", "PICUS", "duration"),
    ("sic", "SIC", "duration"),
    ("dual", "Dual", "duration"),
    ("instructor", "Instructor", "duration"),
    ("examiner", "Examiner", "duration"),
    ("night", "Night", "duration"),
    ("ifr_actual", "IFR actual", "duration"),
    ("ifr_sim", "IFR simulated", "duration"),
    ("xc", "Cross-country", "duration"),
    ("multi_pilot", "Multi-pilot", "duration"),
    ("nvg", "NVG", "duration"),
    ("ldg_day", "Landings day", "count"),
    ("ldg_night", "Landings night", "count"),
    ("ldg_ship", "Ship landings", "count"),
    ("to_day", "Take-offs day", "count"),
    ("to_night", "Take-offs night", "count"),
    ("approach_type", "Approach type", "text"),
    ("approaches", "Approaches", "count"),
    ("pf_pm", "PF/PM", "choice"),
    ("name_pic", "PIC name", "text"),
    ("name_copilot", "Co-pilot", "text"),
    ("name_student", "Student", "text"),
    ("name_instructor", "Instructor name", "text"),
    ("name_examiner", "Examiner name", "text"),
    ("remarks", "Remarks", "text"),
    ("tags", "Tags", "text"),
]

FIELD_NAMES = [f[0] for f in FLIGHT_FIELDS]
FIELD_KIND = {f[0]: f[2] for f in FLIGHT_FIELDS}
FIELD_LABEL = {f[0]: f[1] for f in FLIGHT_FIELDS}
DURATIONS = [f[0] for f in FLIGHT_FIELDS if f[2] == "duration"]
COUNTS = [f[0] for f in FLIGHT_FIELDS if f[2] == "count"]

# Exactly one of these may be logged on an entry (owner decision D5).
ROLES = ["pic", "picus", "sic", "dual"]
ROLE_LABEL = {"pic": "PIC", "picus": "PICUS", "sic": "SIC", "dual": "Dual"}

# Report metrics: key -> (label, kind, SQL aggregate over flight f / aircraft_type t)
METRICS = {"count": ("Entries", "count", "COUNT(*)")}
for _name in DURATIONS + COUNTS:
    METRICS[_name] = (FIELD_LABEL[_name], FIELD_KIND[_name], f"SUM(f.{_name})")
METRICS["ifr"] = ("IFR total", "duration", "SUM(f.ifr_actual + f.ifr_sim)")
METRICS["landings"] = ("Landings total", "count", "SUM(f.ldg_day + f.ldg_night)")
METRICS["total_time"] = ("Flight + sim-only time", "duration",
                         "SUM(CASE WHEN f.flight_time > 0 THEN f.flight_time ELSE f.sim_time END)")

ROLE_SQL = ("CASE WHEN f.pic > 0 THEN 'PIC' WHEN f.picus > 0 THEN 'PICUS' "
            "WHEN f.sic > 0 THEN 'SIC' WHEN f.dual > 0 THEN 'Dual' ELSE '-' END")

# Report dimensions: key -> (label, SQL expression)
DIMENSIONS = {
    "year": ("Year", "substr(f.date, 1, 4)"),
    "month": ("Month", "substr(f.date, 1, 7)"),
    "type_code": ("Type", "f.type_code"),
    "registration": ("Registration", "f.registration"),
    "kind": ("Aircraft / Sim", "CASE WHEN f.is_sim = 1 THEN 'Simulator' ELSE 'Aircraft' END"),
    "category": ("Category", "CASE t.category WHEN 'helicopter' THEN 'Helicopter' WHEN 'aeroplane' THEN 'Aeroplane' "
                             "ELSE 'Other / sim' END"),
    "engines": ("Engines", "CASE t.engines WHEN 'single' THEN 'Single-engine' WHEN 'multi' THEN 'Multi-engine' "
                           "ELSE '-' END"),
    "power": ("Power", "CASE t.power WHEN 'piston' THEN 'Piston' WHEN 'turbine' THEN 'Turbine' ELSE '-' END"),
    "role": ("Role", ROLE_SQL),
    "pf_pm": ("PF/PM", "COALESCE(f.pf_pm, '-')"),
    "dep": ("From", "f.dep"),
    "arr": ("To", "f.arr"),
    "name_pic": ("PIC name", "f.name_pic"),
    "name_copilot": ("Co-pilot", "f.name_copilot"),
    "approach_type": ("Approach type", "f.approach_type"),
    "sim_device": ("Sim device", "f.sim_device"),
}


def hours_to_minutes(value):
    """Decimal hours (number or string) -> integer minutes. Blank -> 0."""
    if value is None or value == "":
        return 0
    return int(round(float(value) * 60))


def minutes_to_hours(minutes):
    return round((minutes or 0) / 60.0, 1)
