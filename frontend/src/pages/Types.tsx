import { useState } from "react";
import { AircraftType, api, ApiError, Meta } from "../api";

function TypeRow({ t, onSaved }: { t: AircraftType; onSaved: () => void }) {
  const [row, setRow] = useState(t);
  const [msg, setMsg] = useState("");
  const dirty = JSON.stringify(row) !== JSON.stringify(t);
  const set = (k: keyof AircraftType, v: string | number) => setRow({ ...row, [k]: v });
  const save = () =>
    api.put(`/api/types/${row.code}`, row).then(() => { setMsg("Saved"); onSaved(); })
      .catch((e) => setMsg(e instanceof ApiError ? e.errors.join(" ") : String(e)));
  return (
    <tr>
      <td><strong>{row.code}</strong></td>
      <td><input value={row.name ?? ""} onChange={(e) => set("name", e.target.value)} /></td>
      <td>
        <select value={row.category} onChange={(e) => set("category", e.target.value)}>
          <option value="helicopter">Helicopter</option>
          <option value="aeroplane">Aeroplane</option>
          <option value="other">Other / sim</option>
        </select>
      </td>
      <td>
        <select value={row.engines ?? ""} onChange={(e) => set("engines", e.target.value)}>
          <option value="">—</option><option value="single">Single</option><option value="multi">Multi</option>
        </select>
      </td>
      <td>
        <select value={row.power ?? ""} onChange={(e) => set("power", e.target.value)}>
          <option value="">—</option><option value="piston">Piston</option><option value="turbine">Turbine</option>
        </select>
      </td>
      <td><input type="checkbox" checked={!!row.multi_pilot} onChange={(e) => set("multi_pilot", e.target.checked ? 1 : 0)} /></td>
      <td>{dirty ? <button className="primary small" onClick={save}>Save</button> : <span className="muted small">{msg}</span>}</td>
    </tr>
  );
}

export default function Types({ meta, onChange }: { meta: Meta; onChange: () => void }) {
  const [code, setCode] = useState("");
  const add = () => {
    if (!code.trim()) return;
    api.put(`/api/types/${code.trim().toUpperCase()}`, { category: "helicopter" }).then(() => { setCode(""); onChange(); });
  };
  return (
    <>
      <div className="page-head">
        <h1>Aircraft types</h1>
        <div className="actions">
          <input placeholder="New type code, e.g. H135" value={code} onChange={(e) => setCode(e.target.value)} />
          <button onClick={add}>Add type</button>
        </div>
      </div>
      <p className="muted">Category, engines and power drive the experience reports (e.g. multi-engine turbine time).
        Fixed-wing types can be added as “Aeroplane”.</p>
      <div className="card table-wrap">
        <table className="table">
          <thead><tr><th>Code</th><th>Name</th><th>Category</th><th>Engines</th><th>Power</th><th>Multi-pilot</th><th></th></tr></thead>
          <tbody>{meta.types.map((t) => <TypeRow key={t.code + JSON.stringify(t)} t={t} onSaved={onChange} />)}</tbody>
        </table>
      </div>
    </>
  );
}
