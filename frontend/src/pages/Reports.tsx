import { useEffect, useMemo, useState } from "react";
import { api, ApiError, fmtCell, Meta, ReportResult, ReportSpec, today } from "../api";

const DEFAULT_SUMMARY = ["count", "flight_time", "pic", "sic", "night", "ifr"];
const DEFAULT_DETAIL = ["date", "dep", "arr", "type_code", "registration", "flight_time", "pic", "sic", "dual",
  "night", "ifr", "ldg_day", "ldg_night", "remarks"];

const TEMPLATES: { name: string; spec: ReportSpec }[] = [
  { name: "Totals by year", spec: { mode: "summary", filters: {}, group_by: ["year"],
    columns: ["count", "flight_time", "pic", "picus", "sic", "dual", "night", "ifr", "nvg"] } },
  { name: "Hours by type", spec: { mode: "summary", filters: {}, group_by: ["type_code"],
    columns: ["count", "flight_time", "pic", "picus", "sic", "dual", "instructor", "night", "ifr", "nvg", "multi_pilot", "landings"] } },
  { name: "Experience summary (CV)", spec: { mode: "summary", filters: { kind: "flight_time" }, group_by: ["engines", "power"],
    columns: ["flight_time", "pic", "sic", "multi_pilot", "night", "ifr_actual", "nvg", "ldg_ship"] } },
  { name: "Simulator sessions", spec: { mode: "detail", filters: { kind: "sim" },
    group_by: [], columns: ["date", "sim_device", "sim_level", "registration", "sim_time", "flight_time", "pic", "picus", "sic", "dual", "ifr_sim", "remarks"] } },
  { name: "Last 12 months, by month", spec: { mode: "summary", filters: { date_from: shift(365) }, group_by: ["month"],
    columns: ["count", "flight_time", "night", "ifr", "nvg", "landings", "ldg_ship"] } },
  { name: "Flights by registration", spec: { mode: "summary", filters: {}, group_by: ["type_code", "registration"],
    columns: ["count", "flight_time"] } },
];

function shift(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

const PRESETS: [string, () => [string, string]][] = [
  ["All time", () => ["", ""]],
  ["This year", () => [`${new Date().getFullYear()}-01-01`, today()]],
  ["Last year", () => { const y = new Date().getFullYear() - 1; return [`${y}-01-01`, `${y}-12-31`]; }],
  ["Last 12 months", () => [shift(365), today()]],
  ["Last 90 days", () => [shift(90), today()]],
  ["Last 28 days", () => [shift(28), today()]],
];

const CONDITIONS = [["night", "Night"], ["ifr", "IFR"], ["nvg", "NVG"], ["multi_pilot", "Multi-pilot"],
  ["xc", "Cross-country"], ["ldg_ship", "Ship landings"]];

function Chips({ options, value, onChange }: { options: { key: string; label: string }[]; value: string[];
  onChange: (v: string[]) => void }) {
  return (
    <div className="chips">
      {options.map((o) => {
        const on = value.includes(o.key);
        return (
          <button type="button" key={o.key} className={`chip ${on ? "on" : ""}`}
            onClick={() => onChange(on ? value.filter((v) => v !== o.key) : [...value, o.key])}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export default function Reports({ meta }: { meta: Meta }) {
  const [spec, setSpec] = useState<ReportSpec>(TEMPLATES[0].spec);
  const [title, setTitle] = useState(TEMPLATES[0].name);
  const [result, setResult] = useState<ReportResult | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [saved, setSaved] = useState<{ id: number; name: string; spec: ReportSpec }[]>([]);

  const loadSaved = () => api.get<typeof saved>("/api/reports/saved").then(setSaved);
  useEffect(() => { loadSaved(); }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      api.post<ReportResult>("/api/reports/run", spec)
        .then((r) => { setResult(r); setErrors([]); })
        .catch((e) => setErrors(e instanceof ApiError ? e.errors : [String(e)]));
    }, 250);
    return () => clearTimeout(t);
  }, [spec]);

  const f = spec.filters;
  const setFilter = (k: string, v: unknown) => setSpec({ ...spec, filters: { ...f, [k]: v } });
  const setMode = (mode: "summary" | "detail") =>
    setSpec({ ...spec, mode, columns: mode === "detail" ? DEFAULT_DETAIL : DEFAULT_SUMMARY, group_by: mode === "detail" ? [] : spec.group_by });
  const load = (name: string, s: ReportSpec) => { setSpec(s); setTitle(name); };

  const columnOptions = useMemo(() => spec.mode === "summary" ? meta.metrics :
    [...meta.fields.filter((x) => !["is_sim", "off_time", "on_time"].includes(x.key)),
      ...meta.metrics.filter((m) => m.key === "ifr" || m.key === "landings")], [spec.mode, meta]);
  const ordered = (keys: string[]) => columnOptions.filter((o) => keys.includes(o.key)).map((o) => o.key);

  const groupSelect = (i: number) => (
    <select value={spec.group_by[i] ?? ""} onChange={(e) => {
      const g = [...spec.group_by];
      if (e.target.value) g[i] = e.target.value; else g.splice(i, 1);
      setSpec({ ...spec, group_by: g.filter(Boolean) });
    }}>
      <option value="">{i === 0 ? "No grouping (totals only)" : "—"}</option>
      {meta.dimensions.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
    </select>
  );

  const exportAs = (format: "csv" | "xlsx") =>
    api.download(`/api/reports/export?format=${format}`, { ...spec, title }, `${title || "report"}.${format}`);

  const saveAs = async () => {
    const name = prompt("Save this report as:", title);
    if (!name) return;
    await api.post("/api/reports/saved", { name, spec });
    setTitle(name);
    loadSaved();
  };

  return (
    <div className="report-layout">
      <aside className="card builder">
        <label className="stack">
          <span>Report</span>
          <select value="" onChange={(e) => {
            const [kind, idx] = e.target.value.split(":");
            if (kind === "t") load(TEMPLATES[+idx].name, TEMPLATES[+idx].spec);
            if (kind === "s") load(saved[+idx].name, saved[+idx].spec);
          }}>
            <option value="">Load a report…</option>
            <optgroup label="Templates">
              {TEMPLATES.map((t, i) => <option key={t.name} value={`t:${i}`}>{t.name}</option>)}
            </optgroup>
            {saved.length > 0 && (
              <optgroup label="Saved">
                {saved.map((s, i) => <option key={s.id} value={`s:${i}`}>{s.name}</option>)}
              </optgroup>
            )}
          </select>
        </label>

        <div className="segmented">
          <button type="button" className={spec.mode === "summary" ? "on" : ""} onClick={() => setMode("summary")}>Totals</button>
          <button type="button" className={spec.mode === "detail" ? "on" : ""} onClick={() => setMode("detail")}>Flight list</button>
        </div>

        <h3>Dates</h3>
        <div className="row2">
          <label className="stack"><span>From</span>
            <input type="date" value={f.date_from ?? ""} onChange={(e) => setFilter("date_from", e.target.value)} /></label>
          <label className="stack"><span>To</span>
            <input type="date" value={f.date_to ?? ""} onChange={(e) => setFilter("date_to", e.target.value)} /></label>
        </div>
        <div className="chips">
          {PRESETS.map(([label, fn]) => (
            <button type="button" key={label} className="chip" onClick={() => {
              const [a, b] = fn();
              setSpec({ ...spec, filters: { ...f, date_from: a, date_to: b } });
            }}>{label}</button>
          ))}
        </div>

        {spec.mode === "summary" && (
          <>
            <h3>Group by</h3>
            {groupSelect(0)}
            {spec.group_by.length > 0 && groupSelect(1)}
          </>
        )}

        <h3>Columns</h3>
        <Chips options={columnOptions} value={spec.columns} onChange={(v) => setSpec({ ...spec, columns: ordered(v) })} />

        <h3>Filters</h3>
        <label className="stack"><span>Entries</span>
          <select value={f.kind ?? ""} onChange={(e) => setFilter("kind", e.target.value)}>
            <option value="">Aircraft and simulator</option>
            <option value="aircraft">Aircraft only</option>
            <option value="sim">Simulator only</option>
            <option value="flight_time">Anything counted as flight time</option>
          </select>
        </label>
        <span className="sub">Aircraft type</span>
        <Chips options={meta.types.map((t) => ({ key: t.code, label: t.code }))} value={f.type_codes ?? []}
          onChange={(v) => setFilter("type_codes", v)} />
        <span className="sub">Role (any of)</span>
        <Chips options={[...meta.roles, { key: "instructor", label: "Instructor" }, { key: "examiner", label: "Examiner" }]}
          value={f.roles ?? []} onChange={(v) => setFilter("roles", v)} />
        <span className="sub">Only entries with</span>
        <Chips options={CONDITIONS.map(([key, label]) => ({ key, label }))} value={f.conditions ?? []}
          onChange={(v) => setFilter("conditions", v)} />
        <div className="row2">
          <label className="stack"><span>PF/PM</span>
            <select value={f.pf_pm ?? ""} onChange={(e) => setFilter("pf_pm", e.target.value)}>
              <option value="">Any</option><option>PF</option><option>PM</option>
            </select></label>
          <label className="stack"><span>Place</span>
            <input list="report-places" value={f.place ?? ""} onChange={(e) => setFilter("place", e.target.value)} /></label>
        </div>
        <datalist id="report-places">{meta.places.map((p) => <option key={p.code} value={p.code} />)}</datalist>
        <label className="stack"><span>Text in remarks / tags / names</span>
          <input value={f.text ?? ""} onChange={(e) => setFilter("text", e.target.value)} /></label>
      </aside>

      <section className="card report">
        <div className="page-head">
          <input className="title-input" value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Report title" />
          <div className="actions">
            <button onClick={saveAs}>Save…</button>
            <button onClick={() => exportAs("csv")}>CSV</button>
            <button onClick={() => exportAs("xlsx")}>Excel</button>
            <button onClick={() => window.print()}>Print</button>
          </div>
        </div>
        <p className="muted small print-meta">
          {f.date_from || f.date_to ? `${f.date_from || "start"} to ${f.date_to || "today"}` : "All dates"}
          {result && spec.mode === "detail" ? ` · ${result.rows.length.toLocaleString()} entries` : ""}
        </p>
        {errors.length > 0 && <div className="alert">{errors.join(" ")}</div>}
        {result && (
          <div className="table-wrap">
            <table className="table report-table">
              <thead>
                <tr>{result.headers.map((h) => <th key={h.key} className={h.kind === "duration" || h.kind === "count" ? "num" : ""}>{h.label}</th>)}</tr>
              </thead>
              <tbody>
                {result.rows.map((r, i) => (
                  <tr key={i}>{r.map((v, j) => {
                    const k = result.headers[j].kind;
                    // Flight list reads like a logbook page: blank instead of zero
                    const blank = spec.mode === "detail" && v === 0;
                    return <td key={j} className={k === "duration" || k === "count" ? "num" : j === r.length - 1 ? "" : "nowrap"}>{blank ? "" : fmtCell(v, k)}</td>;
                  })}</tr>
                ))}
              </tbody>
              <tfoot>
                <tr>{result.totals.map((v, j) => <td key={j} className={result.headers[j].kind === "duration" || result.headers[j].kind === "count" ? "num" : ""}>{fmtCell(v, result.headers[j].kind)}</td>)}</tr>
              </tfoot>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
