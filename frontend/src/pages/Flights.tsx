import { useCallback, useEffect, useState } from "react";
import { api, backTarget, Flight, fmtHours, Meta, openFlight } from "../api";
import FlightForm from "./FlightForm";

const PAGE = 50;
const ROLE = (f: Flight) => (f.pic ? "PIC" : f.picus ? "PICUS" : f.sic ? "SIC" : f.dual ? "Dual" : "");

const editing = (): "new" | number | null => {
  const part = window.location.hash.replace(/^#\/?/, "").split("?")[0].split("/")[1];
  return part === "new" ? "new" : part ? Number(part) : null;
};

export default function Flights({ meta, onChange }: { meta: Meta; onChange: () => void }) {
  const [items, setItems] = useState<Flight[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [type, setType] = useState("");
  const [pfPm, setPfPm] = useState("");
  const [edit, setEdit] = useState(editing);
  // Bulk PF/PM: either a set of picked entries, or "every entry matching the filters"
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [allMatching, setAllMatching] = useState(false);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
    if (q) params.set("q", q);
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    if (type) params.set("type_code", type);
    if (pfPm) params.set("pf_pm", pfPm);
    api.get<{ total: number; items: Flight[] }>(`/api/flights?${params}`).then((r) => {
      setItems(r.items);
      setTotal(r.total);
    });
  }, [q, from, to, type, pfPm, offset]);

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);
  useEffect(() => {
    const onHash = () => setEdit(editing());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => { setOffset(0); setPicked(new Set()); setAllMatching(false); }, [q, from, to, type, pfPm]);

  const count = allMatching ? total : picked.size;
  const pageIds = items.map((f) => f.id!);
  const pageAllPicked = pageIds.length > 0 && pageIds.every((id) => picked.has(id));
  const toggle = (id: number) => {
    const next = new Set(picked);
    if (next.has(id)) next.delete(id); else next.add(id);
    setPicked(next); setAllMatching(false);
  };
  const togglePage = () => {
    const next = new Set(picked);
    pageIds.forEach((id) => (pageAllPicked ? next.delete(id) : next.add(id)));
    setPicked(next); setAllMatching(false);
  };
  const clearSelection = () => { setPicked(new Set()); setAllMatching(false); };

  const applyPfPm = async (value: "PF" | "PM" | null) => {
    const what = value ? `Set ${value}` : "Clear PF/PM";
    if (count > 1 && !confirm(`${what} on ${count.toLocaleString()} entries?`)) return;
    setBusy(true);
    const body = allMatching
      ? { pf_pm: value, filters: { q, date_from: from, date_to: to, type_code: type, pf_pm: pfPm } }
      : { pf_pm: value, ids: [...picked] };
    try {
      const r = await api.post<{ changed: number }>("/api/flights/bulk-pf-pm", body);
      setNotice(`${value ? `${value} set` : "PF/PM cleared"} on ${r.changed.toLocaleString()} entr${r.changed === 1 ? "y" : "ies"}.`);
      clearSelection();
      load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const close = () => (window.location.hash = backTarget());

  if (edit !== null)
    return (
      <FlightForm
        meta={meta}
        flightId={edit === "new" ? null : edit}
        onCancel={close}
        onMetaChange={onChange}
        onSaved={(stay) => {
          load();
          onChange();
          if (!stay) close();
        }}
      />
    );

  return (
    <>
      <div className="page-head">
        <h1>Flights</h1>
        <a className="button primary" href="#/flights/new">+ New entry</a>
      </div>
      <div className="filters card">
        <input placeholder="Search remarks, places, registration, names…" value={q} onChange={(e) => setQ(e.target.value)} />
        <label><span>From</span><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label><span>To</span><input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
        <label>
          <span>Type</span>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All</option>
            {meta.types.map((t) => <option key={t.code}>{t.code}</option>)}
          </select>
        </label>
        <label>
          <span>PF/PM</span>
          <select value={pfPm} onChange={(e) => setPfPm(e.target.value)}>
            <option value="">Any</option>
            <option value="PF">PF</option>
            <option value="PM">PM</option>
            <option value="none">Not set</option>
          </select>
        </label>
      </div>
      {notice && !count && <div className="ok notice" onClick={() => setNotice("")}>{notice}</div>}
      {count > 0 && (
        <div className="bulk-bar card">
          <strong>{count.toLocaleString()} selected</strong>
          {!allMatching && pageAllPicked && total > pageIds.length && (
            <button className="link" onClick={() => setAllMatching(true)}>
              Select all {total.toLocaleString()} matching entries
            </button>
          )}
          {allMatching && <span className="muted small">every entry matching the search and filters</span>}
          <span className="bulk-actions">
            <span className="muted small">PF/PM:</span>
            <button className="primary" disabled={busy} onClick={() => applyPfPm("PF")}>Set PF</button>
            <button className="primary" disabled={busy} onClick={() => applyPfPm("PM")}>Set PM</button>
            <button disabled={busy} onClick={() => applyPfPm(null)}>Clear</button>
            <button className="ghost" onClick={clearSelection}>Cancel</button>
          </span>
        </div>
      )}
      <div className="card table-wrap">
        <table className="table hover">
          <thead>
            <tr>
              <th className="pick" onClick={(e) => e.stopPropagation()}>
                <input type="checkbox" checked={pageAllPicked} onChange={togglePage} aria-label="Select this page" />
              </th>
              <th>Date</th><th>From</th><th>To</th><th>Type</th><th>Reg</th>
              <th className="num">Time</th><th>Role</th><th className="num">Night</th><th className="num">IFR</th>
              <th className="num">Ldg</th><th>Crew</th><th>Remarks</th>
            </tr>
          </thead>
          <tbody>
            {items.map((f) => (
              <tr key={f.id} onClick={() => openFlight(f.id!)} className={allMatching || picked.has(f.id!) ? "picked" : ""}>
                <td className="pick" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={allMatching || picked.has(f.id!)} onChange={() => toggle(f.id!)}
                    aria-label={`Select ${f.date}`} />
                </td>
                <td className="nowrap">{f.date}</td>
                <td>{f.dep}</td>
                <td>{f.arr}</td>
                <td>{f.type_code}{f.is_sim && <span className="badge">SIM{f.sim_level ? ` ${f.sim_level}` : ""}</span>}</td>
                <td>{f.registration}</td>
                <td className="num">{fmtHours(f.flight_time || f.sim_time)}</td>
                <td>{ROLE(f)}{f.pf_pm ? ` · ${f.pf_pm}` : ""}</td>
                <td className="num">{f.night ? fmtHours(f.night) : ""}</td>
                <td className="num">{f.ifr ? fmtHours(f.ifr) : ""}</td>
                <td className="num">{f.ldg_day + f.ldg_night || ""}</td>
                <td className="ellipsis">{[f.name_pic, f.name_copilot].filter((n) => n && n.trim().toUpperCase() !== "SELF").join(", ")}</td>
                <td className="ellipsis">{f.remarks}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!items.length && <p className="muted pad">No entries match.</p>}
      </div>
      <div className="pager">
        <span className="muted">{total.toLocaleString()} entries</span>
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>‹ Newer</button>
        <span>{total ? `${offset + 1}–${Math.min(offset + PAGE, total)}` : ""}</span>
        <button disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Older ›</button>
      </div>
    </>
  );
}
