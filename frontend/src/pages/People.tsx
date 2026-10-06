import { useEffect, useMemo, useState } from "react";
import { api, ApiError, fmtHours } from "../api";

interface Person {
  person: string;
  flights: number;
  hours: number;
  pic: number;
  picus: number;
  sic: number;
  dual: number;
  night: number;
  ifr: number;
  nvg: number;
  sims: number;
  first: string;
  last: string;
  types: string[];
  their_roles: Record<string, number>;
}
interface Bucket { key: string; flights: number; hours: number }
interface Detail {
  person: string;
  flights: number;
  hours: number;
  first: string;
  last: string;
  my_role: Bucket[];
  their_role: Bucket[];
  by_type: Bucket[];
  by_year: Bucket[];
  recent: { id: number; date: string; dep: string; arr: string; type_code: string; registration: string;
    is_sim: number; hours: number; my_role: string; remarks: string | null }[];
}

type SortKey = "hours" | "flights" | "person" | "last";
const ROLE_FILTERS = ["All", "PIC", "Co-pilot", "Instructor", "Examiner", "Student"];

const selected = () => {
  const part = window.location.hash.replace(/^#\/?/, "").split("/").slice(1).join("/");
  return part ? decodeURIComponent(part) : null;
};

function Breakdown({ title, rows, total }: { title: string; rows: Bucket[]; total: number }) {
  return (
    <div>
      <h3>{title}</h3>
      <div className="bars">
        {rows.map((r) => (
          <div key={r.key} className="bar-row wide-label">
            <span className="bar-label">{r.key}</span>
            <span className="bar-track"><span className="bar" style={{ width: `${total ? (r.hours / total) * 100 : 0}%` }} /></span>
            <span className="bar-value">{fmtHours(r.hours)} <span className="muted small">· {r.flights}</span></span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PersonDetail({ name, onRenamed }: { name: string; onRenamed: (to: string) => void }) {
  const [d, setD] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setD(null);
    api.get<Detail>(`/api/people/detail?name=${encodeURIComponent(name)}`).then(setD).catch((e) => setError(e.message));
  }, [name]);

  const rename = async () => {
    const to = prompt(`Rename "${name}" on every entry.\nTo merge two spellings, type the other spelling exactly:`, name);
    if (!to || to === name) return;
    try {
      const r = await api.post<{ changed: number }>("/api/people/rename", { from: name, to });
      alert(`Updated ${r.changed} entr${r.changed === 1 ? "y" : "ies"}.`);
      onRenamed(to.trim());
    } catch (e) {
      alert(e instanceof ApiError ? e.errors.join(" ") : String(e));
    }
  };

  if (error) return <div className="alert">{error}</div>;
  if (!d) return <p className="muted">Loading…</p>;
  const maxYear = Math.max(...d.by_year.map((y) => y.hours));
  return (
    <>
      <div className="page-head">
        <h2 className="person-name">{d.person}</h2>
        <button onClick={rename}>Rename / merge…</button>
      </div>
      <div className="tiles tiles-small">
        <div className="tile"><div className="tile-label">Hours together</div><div className="tile-value">{fmtHours(d.hours)}</div></div>
        <div className="tile"><div className="tile-label">Entries</div><div className="tile-value">{d.flights}</div></div>
        <div className="tile"><div className="tile-label">First</div><div className="tile-value date">{d.first}</div></div>
        <div className="tile"><div className="tile-label">Last</div><div className="tile-value date">{d.last}</div></div>
      </div>
      <div className="grid-2 tight">
        <Breakdown title="Their role" rows={d.their_role} total={d.hours} />
        <Breakdown title="My role" rows={d.my_role} total={d.hours} />
        <Breakdown title="By type" rows={d.by_type} total={d.hours} />
        <div>
          <h3>By year</h3>
          <div className="year-strip">
            {d.by_year.map((y) => (
              <div key={y.key} className="year" title={`${y.key}: ${fmtHours(y.hours)} h, ${y.flights} entries`}>
                <span className="year-bar" style={{ height: `${maxYear ? Math.max(4, (y.hours / maxYear) * 60) : 4}px` }} />
                <span className="year-label">{y.key.slice(2)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <h3>Entries together</h3>
      <div className="table-wrap people-flights">
        <table className="table hover compact">
          <thead><tr><th>Date</th><th>Route</th><th>Type</th><th>Reg</th><th className="num">Time</th><th>My role</th><th>Remarks</th></tr></thead>
          <tbody>
            {d.recent.map((f) => (
              <tr key={f.id} onClick={() => (window.location.hash = `#/flights/${f.id}`)}>
                <td className="nowrap">{f.date}</td>
                <td className="nowrap">{f.dep}{f.arr && f.arr !== f.dep ? ` – ${f.arr}` : ""}</td>
                <td>{f.type_code}{f.is_sim ? <span className="badge">SIM</span> : null}</td>
                <td>{f.registration}</td>
                <td className="num">{fmtHours(f.hours)}</td>
                <td>{f.my_role}</td>
                <td className="ellipsis">{f.remarks}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function People() {
  const [people, setPeople] = useState<Person[]>([]);
  const [q, setQ] = useState("");
  const [role, setRole] = useState("All");
  const [sort, setSort] = useState<SortKey>("hours");
  const [sel, setSel] = useState(selected);

  const load = () => api.get<Person[]>("/api/people").then(setPeople);
  useEffect(() => {
    load();
    const onHash = () => setSel(selected());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const shown = useMemo(() => {
    const list = people.filter((p) => (!q || p.person.toLowerCase().includes(q.toLowerCase())) &&
      (role === "All" || p.their_roles[role]));
    const by: Record<SortKey, (a: Person, b: Person) => number> = {
      hours: (a, b) => b.hours - a.hours,
      flights: (a, b) => b.flights - a.flights,
      person: (a, b) => a.person.localeCompare(b.person),
      last: (a, b) => b.last.localeCompare(a.last),
    };
    return [...list].sort(by[sort]);
  }, [people, q, role, sort]);

  const open = (name: string) => (window.location.hash = `#/people/${encodeURIComponent(name)}`);
  const th = (key: SortKey, label: string, num = false) => (
    <th className={`sortable ${num ? "num" : ""} ${sort === key ? "sorted" : ""}`} onClick={() => setSort(key)}>{label}</th>
  );

  return (
    <>
      <div className="page-head">
        <h1>People</h1>
        <span className="muted">{people.length} people flown with</span>
      </div>
      <div className="people-layout">
        <section className="card people-list">
          <input placeholder="Search names" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="chips">
            {ROLE_FILTERS.map((r) => (
              <button key={r} type="button" className={`chip ${role === r ? "on" : ""}`} onClick={() => setRole(r)}>
                {r === "All" ? "All" : r === "PIC" ? "As PIC" : `As ${r.toLowerCase()}`}
              </button>
            ))}
          </div>
          <div className="table-wrap">
            <table className="table hover compact">
              <thead><tr>{th("person", "Name")}{th("hours", "Hours", true)}{th("flights", "Entries", true)}{th("last", "Last")}</tr></thead>
              <tbody>
                {shown.map((p) => (
                  <tr key={p.person} className={sel === p.person ? "selected" : ""} onClick={() => open(p.person)}>
                    <td>
                      <div>{p.person}</div>
                      <div className="muted small">{Object.keys(p.their_roles).join(" · ")} · {p.types.join(", ")}</div>
                    </td>
                    <td className="num">{fmtHours(p.hours)}</td>
                    <td className="num">{p.flights}</td>
                    <td className="nowrap muted small">{p.last}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!shown.length && <p className="muted pad">No one matches.</p>}
          </div>
        </section>
        <section className="card person-detail">
          {sel ? (
            <PersonDetail key={sel} name={sel} onRenamed={(to) => { load(); open(to); }} />
          ) : (
            <div className="empty"><p className="muted">Choose someone to see your flying together.</p></div>
          )}
        </section>
      </div>
    </>
  );
}
