# Logbook

A personal pilot logbook that runs on your own computer, in the browser. It is helicopter-first,
with fixed-wing support built into the data model.

- **Flights:** add, edit and search entries. Rules are enforced: one role per entry, and
  IFR = actual + simulated.
- **Report builder:** pick dates, filters, grouping and columns, then export to Excel or CSV,
  or print.
- **Import:** your FLYLOG Excel export, with your corrections applied.
- **Your data stays local** in `data/logbook.db`. Back it up from the *Import & backup* page.

See [docs/PLAN.md](docs/PLAN.md) for the plan, the decisions made so far, and what comes next.

## Set up (once)

You need Python 3.10+ and Node.js 20+. On Ubuntu/Debian:
`sudo apt install python3-venv nodejs npm`.

```bash
git clone https://github.com/richardsmoffatt/Logbook.git
cd Logbook
./logbook.sh setup
```

## Import your logbook (once)

Keep your export and your corrections file **outside this folder, or in `data/`**. Both are
private, and this repository is public.

```bash
./logbook.sh import ~/Documents/FLYLOG-Export.xlsx --corrections ~/Documents/logbook-corrections.json
```

If any entry breaks the logbook rules, nothing is imported and the problem rows are listed.
To redo the import later, add `--replace`. This keeps flights you entered in the app.

## Run

```bash
./logbook.sh            # opens http://localhost:8000
./logbook.sh serve --host 0.0.0.0   # also reachable from a phone/iPad on your home network
```

## Development

```bash
./logbook.sh test                       # backend tests + frontend typecheck
cd frontend && npm run dev              # live-reloading UI on :5173 (run ./logbook.sh alongside)
```
