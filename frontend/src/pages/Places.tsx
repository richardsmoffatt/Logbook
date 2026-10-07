import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, Place } from "../api";

const KINDS = ["aerodrome", "heliport", "HLS", "rig", "ship", "hospital", "field", "other"];

const EDITABLE = ["name", "kind", "lat", "lon", "notes"] as const;
const same = (a: unknown, b: unknown) => String(a ?? "") === String(b ?? "");

type Track = (code: string, save: (() => Promise<void>) | null) => void;

function PlaceRow({ p, onSaved, onTrack, hidden }: { p: Place; onSaved: () => void; onTrack: Track; hidden: boolean }) {
  const [row, setRow] = useState(p);
  const [saved, setSaved] = useState(p);              // last values the server accepted
  const [status, setStatus] = useState<"" | "saved" | "error">("");
  const [error, setError] = useState("");
  const dirty = EDITABLE.some((k) => !same(row[k], saved[k]));
  const set = (k: keyof Place, v: string) => { setRow({ ...row, [k]: v }); setStatus(""); };
  const save = (): Promise<void> =>
    api.put<Place>(`/api/places/${row.code}`, row)
      .then((result) => {
        const next = { ...row, ...result };
        setRow(next); setSaved(next); setStatus("saved"); setError("");
        onSaved();
      })
      .catch((e) => { setStatus("error"); setError(e instanceof ApiError ? e.errors.join(" ") : String(e)); });
  useEffect(() => {
    onTrack(p.code, dirty ? save : null);
    return () => onTrack(p.code, null);
  }, [dirty, row]); // save() reads the current row

  return (
    <tr className={dirty ? "row-dirty" : status === "saved" ? "row-saved" : ""} hidden={hidden}>
      <td><strong>{row.code}</strong></td>
      <td><input value={row.name ?? ""} onChange={(e) => set("name", e.target.value)} /></td>
      <td>
        <select value={row.kind ?? ""} onChange={(e) => set("kind", e.target.value)}>
          <option value="">—</option>{KINDS.map((k) => <option key={k}>{k}</option>)}
        </select>
      </td>
      <td><input className="coord" value={row.lat ?? ""} onChange={(e) => set("lat", e.target.value)} placeholder="lat" /></td>
      <td><input className="coord" value={row.lon ?? ""} onChange={(e) => set("lon", e.target.value)} placeholder="lon" /></td>
      <td className="num">{row.flights}</td>
      <td className="muted nowrap">{row.last_visit}</td>
      <td className="nowrap">
        {dirty && <button className="primary small" onClick={save}>Save</button>}
        {!dirty && status === "saved" && <span className="saved-mark">✓ Saved</span>}
        {status === "error" && <div className="error-text small">{error}</div>}
      </td>
    </tr>
  );
}

export default function Places({ onChange }: { onChange: () => void }) {
  const [places, setPlaces] = useState<Place[]>([]);
  const [q, setQ] = useState("");
  const [missing, setMissing] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get<Place[]>("/api/places").then(setPlaces); }, []);
  const visible = (p: Place) =>
    (!q || `${p.code} ${p.name ?? ""}`.toLowerCase().includes(q.toLowerCase())) && (!missing || p.lat === null);

  // Rows with unsaved edits register their save function here, for "Save all"
  const pending = useRef(new Map<string, () => Promise<void>>());
  const [pendingCount, setPendingCount] = useState(0);
  const track = useCallback<Track>((code, save) => {
    if (save) pending.current.set(code, save); else pending.current.delete(code);
    setPendingCount(pending.current.size);
  }, []);
  const saveAll = async () => {
    setBusy(true);
    for (const save of [...pending.current.values()]) await save();
    setBusy(false);
  };
  return (
    <>
      <div className="page-head">
        <h1>Places</h1>
        <div className="actions">
          {pendingCount > 0 && (
            <button className="primary" disabled={busy} onClick={saveAll}>
              {busy ? "Saving…" : `Save all (${pendingCount})`}
            </button>
          )}
          <input placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
          <label className="check"><input type="checkbox" checked={missing} onChange={(e) => setMissing(e.target.checked)} /> No coordinates</label>
        </div>
      </div>
      <p className="muted">Every place you have landed. Non-ICAO sites (rigs, ships, HLS) can be given a name and decimal lat/long.</p>
      <div className="card table-wrap">
        <table className="table">
          <thead><tr><th>Code</th><th>Name</th><th>Kind</th><th>Lat</th><th>Lon</th><th className="num">Flights</th><th>Last visit</th><th></th></tr></thead>
          {/* Filtered-out rows are hidden, not removed, so unsaved edits survive a search */}
          <tbody>{places.map((p) => <PlaceRow key={p.code} p={p} onSaved={onChange} onTrack={track} hidden={!visible(p)} />)}</tbody>
        </table>
      </div>
    </>
  );
}
