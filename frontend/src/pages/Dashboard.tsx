import { useEffect, useState } from "react";
import { api, fmtHours, Summary } from "../api";

const TOTALS: [string, string][] = [
  ["flight_time", "Total flight time"],
  ["pic", "PIC"],
  ["sic", "SIC"],
  ["picus", "PICUS"],
  ["dual", "Dual"],
  ["instructor", "Instructor"],
  ["night", "Night"],
  ["ifr", "IFR"],
  ["nvg", "NVG"],
  ["sim_time", "Simulator"],
];

export default function Dashboard() {
  const [s, setS] = useState<Summary | null>(null);
  useEffect(() => {
    api.get<Summary>("/api/summary").then(setS);
  }, []);
  if (!s) return <p className="muted">Loading…</p>;
  if (!s.entries)
    return (
      <div className="empty">
        <h2>No flights yet</h2>
        <p>
          Import your FLYLOG export on the <a href="#/data">Import &amp; backup</a> page, or{" "}
          <a href="#/flights/new">add a flight</a>.
        </p>
      </div>
    );
  const max = Math.max(...s.by_type.map((t) => t.hours));
  return (
    <>
      <div className="page-head">
        <h1>Dashboard</h1>
        <span className="muted">
          {s.entries.toLocaleString()} entries · {s.first} to {s.last}
        </span>
      </div>
      <section className="tiles">
        {TOTALS.map(([key, label], i) => (
          <div key={key} className={`tile ${i === 0 ? "tile-hero" : ""}`}>
            <div className="tile-label">{label}</div>
            <div className="tile-value">{fmtHours(s.totals[key])}</div>
          </div>
        ))}
      </section>
      <div className="grid-2">
        <section className="card">
          <h2>Recent flying</h2>
          <table className="table compact">
            <tbody>
              {s.periods.map((p) => (
                <tr key={p.label}>
                  <td>{p.label}</td>
                  <td className="num">{fmtHours(p.hours)} h</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h2>Last 90 days</h2>
          <table className="table compact">
            <thead>
              <tr>
                <th></th>
                <th className="num">90 days</th>
                <th className="num">Last logged</th>
              </tr>
            </thead>
            <tbody>
              {s.currency.map((c) => (
                <tr key={c.label}>
                  <td>{c.label}</td>
                  <td className="num">{c.label.includes("hours") ? fmtHours(c.last_90) : c.last_90}</td>
                  <td className="num muted">{c.last ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">
            Regulatory currency rules (per authority) come with the reports phase; these are raw counts.
          </p>
        </section>
        <section className="card">
          <h2>Flight time by type</h2>
          <div className="bars">
            {s.by_type.map((t) => (
              <div key={t.type_code} className="bar-row">
                <span className="bar-label">{t.type_code}</span>
                <span className="bar-track">
                  <span className="bar" style={{ width: `${(t.hours / max) * 100}%` }} />
                </span>
                <span className="bar-value">{fmtHours(t.hours)}</span>
              </div>
            ))}
          </div>
          <p className="muted small">Includes Level D simulator time, which counts as flight time.</p>
        </section>
      </div>
    </>
  );
}
