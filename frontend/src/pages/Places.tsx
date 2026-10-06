import { useEffect, useState } from "react";
import { api, ApiError, Place } from "../api";

const KINDS = ["aerodrome", "heliport", "HLS", "rig", "ship", "hospital", "field", "other"];

function PlaceRow({ p, onSaved }: { p: Place; onSaved: () => void }) {
  const [row, setRow] = useState(p);
  const [msg, setMsg] = useState("");
  const dirty = ["name", "kind", "lat", "lon", "notes"].some((k) => (row as never)[k] !== (p as never)[k]);
  const set = (k: keyof Place, v: string) => setRow({ ...row, [k]: v });
  const save = () =>
    api.put<Place>(`/api/places/${row.code}`, row).then((saved) => { setRow({ ...row, ...saved }); setMsg("Saved"); onSaved(); })
      .catch((e) => setMsg(e instanceof ApiError ? e.errors.join(" ") : String(e)));
  return (
    <tr>
      <td><strong>{row.code}</strong></td>
      <td><input value={row.name ?? ""} onChange={(e) => set("name", e.target.value)} /></td>
      <td>
        <select value={row.kind ?? ""} onChange={(e) => set("kind", e.target.value)}>
          <option value="">—</option>{KINDS.map((k) => <option key={k}>{k}</option>)}
        </select>
      </td>
      <td><input className="coord" value={row.lat ?? ""} onChange={(e) => set("lat", e.target.value)} placeholder="24.4539" /></td>
      <td><input className="coord" value={row.lon ?? ""} onChange={(e) => set("lon", e.target.value)} placeholder="54.3773" /></td>
      <td className="num">{row.flights}</td>
      <td className="muted nowrap">{row.last_visit}</td>
      <td>{dirty ? <button className="primary small" onClick={save}>Save</button> : <span className="muted small">{msg}</span>}</td>
    </tr>
  );
}

export default function Places({ onChange }: { onChange: () => void }) {
  const [places, setPlaces] = useState<Place[]>([]);
  const [q, setQ] = useState("");
  const [missing, setMissing] = useState(false);
  useEffect(() => { api.get<Place[]>("/api/places").then(setPlaces); }, []);
  const shown = places.filter((p) =>
    (!q || `${p.code} ${p.name ?? ""}`.toLowerCase().includes(q.toLowerCase())) && (!missing || p.lat === null));
  return (
    <>
      <div className="page-head">
        <h1>Places</h1>
        <div className="actions">
          <input placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
          <label className="check"><input type="checkbox" checked={missing} onChange={(e) => setMissing(e.target.checked)} /> No coordinates</label>
        </div>
      </div>
      <p className="muted">Every place you have landed. Non-ICAO sites (rigs, ships, HLS) can be given a name and decimal lat/long.</p>
      <div className="card table-wrap">
        <table className="table">
          <thead><tr><th>Code</th><th>Name</th><th>Kind</th><th>Lat</th><th>Lon</th><th className="num">Flights</th><th>Last visit</th><th></th></tr></thead>
          <tbody>{shown.map((p) => <PlaceRow key={p.code} p={p} onSaved={onChange} />)}</tbody>
        </table>
      </div>
    </>
  );
}
