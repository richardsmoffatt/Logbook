# Pilot Logbook App — Plan (draft v0.1)

Status: **draft, awaiting answers to the open questions in section 8.**

## 1. Goals

1. Import the existing FLYLOG export (≈10,000 hrs, 4,044 entries, 1992 → present) losslessly.
2. Add, edit, and delete flights quickly, on desktop and on a phone/tablet.
3. Produce reports for any date range (totals, by type/role/condition, currency, experience summaries).
4. Produce printable logbooks (PDF) in a chosen layout, with page totals and brought-forward totals.
5. Helicopter only at first, with the data model ready for fixed-wing later.

## 2. What the source file contains

| Item | Value |
|---|---|
| Entries | 4,044 |
| Date range | 1992-05-19 → 2026-10-05 (no entries in 1994) |
| Block total | 9,986.7 h, of which 292.5 h is on `SIM` rows, leaving **≈9,694.2 h aircraft** |
| PIC / PICUS / SIC / Dual / Instructor | 6,350.7 / 100.5 / 3,139.2 / 444.2 / 291.2 |
| Night / IFR (actual + simulated) / XC | 973.0 / 781.7 (588.2 + 151.8) / 68.1 |
| Multi-pilot | 9,248.6 |
| Simulator (`DURATION_SIMULATOR`) | 306.8 h over 129 sessions |
| Landings day / night | 13,072 / 1,260 |

Hours by type: S76 5,041.6 · A139 3,741.9 · R22 488.5 · SIM 292.5 · A109 193.0 · B06 118.0 · B47G 86.5 · AS55 23.8 · AS50 0.9

Columns that are always empty in the export: `TIME_BLOCK_END`, `PERSONAL_NOTE`, `NAME_PICUS`,
`NAME_ATTENDANT`, `TIME_TAKEOFF`, `TIME_LANDING`, `TIME_DUTY_*`, `DURATION_DUTY`, `DURATION_EXAMINER`,
`FLIGHT_NUMBER`. `TIME_BLOCK_START` is `00:00` on 3,942 rows, which looks like a placeholder.

## 3. Data-quality findings (to confirm with the owner)

1. **Exact duplicates:** 6 rows are exact copies of another row (2001-02-13 VH-HBY, 2009-05-06/07/12
   B-MHG/B-MHF/B-KCC/B-MHH, 2015-02-20 AW139 sim). They are likely double entries worth about 13.8 h.
2. **Sim time counted as flight time:** 122 of the 131 `SIM` rows also have `DURATION_BLOCK` and
   PIC/SIC/Dual filled in, so the 9,986.7 block total includes sim time.
3. **Sims that may be logged as aircraft:** registration `AUH139` is on type `A139` with routes such
   as KLGA→KEWR and LIRU→LIRA ("Hot and heavy training"). These look like sim sessions.
4. **Two roles on one flight:** 26 rows credit the full block time to both PIC and Dual (or PIC and
   SIC). Examples: 1992-06-10 R22, 2002–2004 S76 Songkhla/Yangon training, and the 2008-09 sim sorties.
5. **NVG column has mixed units:** most values are milliseconds (3,600,000 = 1.0 h), about 45.0 h in
   total. Six rows hold small integers (3, 4, 5), which could be NVG landings or hours. Separately,
   20 rows have an `NVG` tag.
6. **`SHIPS` column:** this looks like a count of deck landings (207 in total, mostly A109).
7. **IFR breakdown:** on 37 rows, IFR ≠ IFR actual + IFR simulated.
8. **Night time without night landings:** 212 flights. This matters for night-currency calculations.
9. **Non-ICAO location codes:** EZULU, HAZZA, RYRPA, QCOL, QLFD, YUOF, etc. These are probably rigs,
   ships, or HLS sites, so we need a "places" table with names and optional coordinates.
10. **Non-standard registrations:** LIW08–LIW99 (fleet/serial numbers?), and sim "registrations"
    such as AW139, S76, AW109GRANDNEW, ATC810. Two sim rows have no registration.

Proposed handling: the importer keeps every raw value unchanged in an `import_raw` record. It then
writes normalised values and attaches a **review flag** to each row with a problem, and the app gets
a "Review imported data" screen. Nothing is changed or deleted without the owner's approval.

## 4. Proposed architecture (subject to Q1–Q3)

- **Front end:** React + TypeScript, built as an installable PWA (works offline on iPad, phone, laptop).
- **Storage:** SQLite. Either local-first in the browser (with backup/export) or a small hosted
  backend with sync (see Q2).
- **Time storage:** integer minutes. Display as decimal hours (one decimal place) or HH:MM per user setting.
- **PDF output:** generated server-side or in the browser with a print-layout engine. Also CSV/XLSX export.
- **Tests:** the importer is verified against the totals in section 2, so we can prove nothing was lost.

## 5. Data model (first cut)

- `flight`: date, departure, arrival, route (via points), aircraft_id, block off/on (optional),
  total, role times (PIC, PICUS, SIC, dual, instructor, examiner), condition times (night, IFR actual,
  IFR simulated, XC, NVG, multi-pilot), takeoffs/landings (day, night, NVG, deck), approaches
  (type + count), crew names, remarks, tags, sim session link
- `aircraft`: registration, type
- `aircraft_type`: ICAO designator, make/model, **category (helicopter / aeroplane)**, engine count,
  engine type (piston/turbine), single/multi-pilot certification, class/type-rating group
- `sim_session`: device type (FFS/FTD/FNPT), device ID, qualification level. Kept separate from
  aircraft time.
- `place`: code, name, kind (aerodrome / HLS / rig / ship), coordinates (optional)
- `person`: crew names, normalised for spelling variants
- `tag`: free tags (NVG, OFFSHORE, FORMATION, MPT, PF/PM, …)

Initial type table (please check):

| Type | Category | Engines | Power | Ops |
|---|---|---|---|---|
| R22 | Helicopter | Single | Piston | SP |
| B47G | Helicopter | Single | Piston | SP |
| B06 | Helicopter | Single | Turbine | SP |
| AS50 (AS350) | Helicopter | Single | Turbine | SP |
| AS55 (AS355) | Helicopter | Twin | Turbine | SP/MP |
| A109 | Helicopter | Twin | Turbine | MP |
| S76 | Helicopter | Twin | Turbine | MP |
| A139 (AW139) | Helicopter | Twin | Turbine | MP |

## 6. Features by phase

**Phase 1: foundation.** Importer with review screen, flight list with search/filter, add/edit
flight form (defaults from last flight, crew/place autocomplete, quick-add buttons), aircraft and
place management, backup/export.

**Phase 2: reports.** Totals for any date range; grouping by type, registration, role, condition,
year, or month; currency dashboard (day/night landings in 90 days, NVG, deck, IFR/approaches);
flight-time limits (28 days, 90 days, 12 months, calendar year); experience summary for CVs and
job applications; and CSV/XLSX/PDF output.

**Phase 3: printable logbooks.** Paginated PDF logbook in the chosen regulator layout, with page
totals, brought-forward totals, and a certification/signature block. Also a summary page per
licence application.

**Phase 4: extras.** Fixed-wing support (SEP/MEP/class ratings), automatic night calculation from
block times and coordinates, documents (medical, licence, rating expiries with reminders), and a
map of places flown.

## 7. Milestones

1. Repository scaffold plus the importer, with tests that match the source totals exactly.
2. Data review session with the owner, so we can fix or confirm the items in section 3.
3. CRUD UI, then reports, then the PDF logbook. A usable build is delivered after each step.

## 8. Decisions log

| # | Decision | Date |
|---|---|---|
| D1 | The source `DURATION_BLOCK` column is **flight time**. It imports as `flight_time`, and the app labels the main column "Flight time", not "Block". | 2026-10-06 |
| D2 | Level D full-flight-simulator time **counts as flight time** and is included in totals. The sim session is still recorded (device + level) so it can be reported separately when needed. | 2026-10-06 |
| D3 | Duplicates (finding 1): the owner is checking them. Leave as-is and flag them until we hear back. | 2026-10-06 (pending) |
| D4 | `AUH139` entries are simulator sessions. They will be re-typed as AW139 Level D sim and still counted as flight time (D2). | 2026-10-06 |
| D5 | **Exactly one of PIC / PICUS / SIC / Dual per entry.** The app enforces this on entry. Instructor and examiner remain extra roles on top of PIC. The 31 imported entries that break this rule are being reviewed by the owner. | 2026-10-06 (review pending) |
| D6 | All times are **decimal hours** (one decimal place). | 2026-10-06 |
| D7 | NVG: the millisecond values convert to hours (45.0 h in total, which the owner confirms is about right). The 6 small integer values are under review. | 2026-10-06 |
| D8 | `SHIPS` = ship/deck landings, and they **feed into currency**. | 2026-10-06 |
| D9 | Non-ICAO location codes are real landing sites. Each gets a `place` record with a name and lat/long, filled in gradually. The app supports unlisted sites and ad-hoc lat/long. | 2026-10-06 |
| D10 | LIW08–LIW99 are UAE military serials. Keep them as-is; the app permits non-civil registrations. | 2026-10-06 |
| D11 | Night flights with no night landings are normally ones where the owner was PM. Add PF/PM per flight, and only PF landings count toward currency. Import leaves these entries as they are. | 2026-10-06 |
| D12 | The 37 IFR entries where total ≠ actual + simulated are under owner review (possibly VFR into IFR). The app will require IFR total = actual + simulated on entry. | 2026-10-06 (review pending) |

Owner review file: `Logbook-Data-Review.xlsx`, generated from the export and not committed
because it contains personal data. Tabs: Two roles (31), IFR mismatch (37), Duplicates (12 rows /
6 pairs), NVG small values (6), AUH139 sim (11, for information).

Effect of D2 on the data:
- Two AW139 Level D sessions have sim time but no flight time: 2024-10-08 ("semiannual", 4.0 h) and
  2025-01-13 ("Sim recurrent", 4.0 h). Proposal: credit 4.0 h flight time to each, adding 8.0 h.
- Two AW139 sessions have flight time but no sim duration: 2017-02-11 and 2022-08-17 (2.0 h each).
  Proposal: fill in the sim duration.
- Five Generic ATC-810 sessions from 1997/2001 (10.3 h) have sim time only. The ATC-810 is a basic
  instrument trainer, not a Level D device, so the proposal is to keep these as sim-only. Awaiting confirmation.

## 9. Open questions

See the conversation, or the copy below, which we will update as answers come in.

- Q1 Devices/platform · Q2 Hosting and backup · Q3 Single or multiple users
- Q4 Licensing authority(ies) and the logbook layout(s) to print
- Q5 Reports needed (and for what purpose)
- Q6 Decimal vs HH:MM; whether block times are logged for new flights
- Q7–Q14 Data-quality items from section 3
