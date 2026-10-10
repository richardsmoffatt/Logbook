import { useEffect, useMemo, useState } from "react";
import { api, ApiError, backLabel, Flight, Meta, today } from "../api";
import CustomFieldsDialog from "./CustomFieldsDialog";

type Draft = Record<string, string | boolean>;
const ROLES = ["pic", "picus", "sic", "dual"] as const;
const ROLE_LABEL: Record<string, string> = { pic: "PIC", picus: "PICUS", sic: "SIC", dual: "Dual" };
const USER_HOURS = ["uh1", "uh2", "uh3", "uh4", "uh5"];
const USER_NUMBERS = ["un1", "un2", "un3", "un4", "un5"];
const HOURS = ["flight_time", "sim_time", "instructor", "examiner", "night", "ifr_actual", "ifr_sim", "xc",
  "multi_pilot", ...USER_HOURS];
const COUNTS = ["ldg_day", "ldg_night", "to_day", "to_night", "approaches", ...USER_NUMBERS];

function toDraft(f: Partial<Flight>): Draft {
  const d: Draft = {};
  for (const [k, v] of Object.entries(f)) {
    if (typeof v === "boolean") d[k] = v;
    else if (typeof v === "number") d[k] = v ? String(v) : "";
    else d[k] = v ?? "";
  }
  d.role = ROLES.find((r) => Number(f[r])) ?? "";
  return d;
}

function fromDraft(d: Draft): Partial<Flight> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(d)) {
    if (k === "role" || k === "id" || k === "ifr") continue;
    if (HOURS.includes(k) || COUNTS.includes(k)) out[k] = v === "" ? 0 : Number(v);
    else out[k] = v === "" ? null : v;
  }
  const role = d.role as string;
  const roleTime = Number(d.flight_time || 0) || Number(d.sim_time || 0);
  for (const r of ROLES) out[r] = r === role ? roleTime : 0;
  return out as Partial<Flight>;
}

const isSelf = (v: unknown) => String(v ?? "").trim().toUpperCase() === "SELF";

/** SIC: you are the co-pilot, so SELF goes in Co-pilot and PIC name is the captain (owner decision D21).
 *  Switching between PIC and SIC swaps the two names, as the other pilot's seat swaps with yours. */
function crewForRole(d: Draft, role: string, previous: string) {
  const pic = String(d.name_pic ?? ""), copilot = String(d.name_copilot ?? "");
  if (role === "sic") {
    if (previous === "pic" && isSelf(pic)) [d.name_pic, d.name_copilot] = [isSelf(copilot) ? "" : copilot, "SELF"];
    else {
      if (isSelf(pic)) d.name_pic = "";
      if (!copilot || isSelf(copilot)) d.name_copilot = "SELF";
    }
  } else if (previous === "sic" && isSelf(copilot)) {
    if (role === "pic") [d.name_pic, d.name_copilot] = ["SELF", pic];
    else d.name_copilot = "";
  } else if (role === "pic" && !pic) d.name_pic = "SELF";
}

interface Props {
  meta: Meta;
  flightId: number | null;
  onSaved: (stay: boolean) => void;
  onMetaChange: () => void;
  onCancel: () => void;
}

export default function FlightForm({ meta, flightId, onSaved, onCancel, onMetaChange }: Props) {
  const [d, setD] = useState<Draft | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [managing, setManaging] = useState(false);

  useEffect(() => {
    setErrors([]);
    if (flightId) {
      api.get<Flight>(`/api/flights/${flightId}`).then((f) => setD(toDraft(f)));
    } else {
      api.get<Flight | null>("/api/flights/last").then((last) => {
        const base = toDraft({ date: today(), is_sim: false, name_pic: "SELF" });
        if (last && !last.is_sim) {
          Object.assign(base, {
            type_code: last.type_code, registration: last.registration ?? "", dep: last.arr ?? "",
            arr: last.arr ?? "", role: ROLES.find((r) => last[r]) ?? "pic",
            multi_pilot: "",
          });
          crewForRole(base, String(base.role), "");
        }
        setD(base);
      });
    }
  }, [flightId]);

  const type = useMemo(() => meta.types.find((t) => t.code === d?.type_code), [meta.types, d?.type_code]);
  if (!d) return <p className="muted">Loading…</p>;

  const set = (k: string, v: string | boolean) => {
    const next = { ...d, [k]: v };
    if (k === "registration") {
      const reg = meta.registrations.find((r) => r.registration === String(v).toUpperCase());
      if (reg) next.type_code = reg.type_code;
    }
    if (k === "is_sim" && !v) Object.assign(next, { sim_time: "", sim_device: "", sim_level: "" });
    // Level D sim time counts as flight time (owner decision D2)
    if ((k === "sim_time" || k === "sim_level") && next.is_sim && next.sim_level === "D") next.flight_time = next.sim_time;
    if (k === "role") crewForRole(next, String(v), String(d.role));
    // Multi-pilot types: multi-pilot time follows flight time until edited separately
    if (k === "flight_time" && type?.multi_pilot && !next.is_sim && String(d.multi_pilot ?? "") === String(d.flight_time ?? ""))
      next.multi_pilot = v;
    setD(next);
  };

  const field = (k: string, label: string, opts: { type?: string; list?: string; step?: string; wide?: boolean;
    upper?: boolean; placeholder?: string } = {}) => (
    <label className={opts.wide ? "wide" : ""}>
      <span>{label}</span>
      <input
        type={opts.type ?? "text"}
        step={opts.step}
        min={opts.type === "number" ? 0 : undefined}
        list={opts.list}
        placeholder={opts.placeholder}
        value={String(d[k] ?? "")}
        onChange={(e) => set(k, opts.upper ? e.target.value.toUpperCase() : e.target.value)}
      />
    </label>
  );
  const hours = (k: string, label: string) => field(k, label, { type: "number", step: "0.1" });
  const count = (k: string, label: string) => field(k, label, { type: "number", step: "1" });

  const save = async (addAnother: boolean) => {
    setSaving(true);
    setErrors([]);
    try {
      const body = fromDraft(d);
      if (flightId) await api.put(`/api/flights/${flightId}`, body);
      else await api.post("/api/flights", body);
      if (addAnother) {
        setD({ ...d, id: "", remarks: "", flight_time: "", night: "", ifr_actual: "", ifr_sim: "", xc: "",
          ldg_day: "", ldg_night: "", to_day: "", to_night: "", approaches: "", approach_type: "",
          multi_pilot: "", instructor: "", examiner: "", dep: d.arr,
          ...Object.fromEntries([...USER_HOURS, ...USER_NUMBERS].map((k) => [k, ""])) });
      }
      onSaved(addAnother);
    } catch (e) {
      setErrors(e instanceof ApiError ? e.errors : [String(e)]);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!flightId || !confirm("Delete this entry? This cannot be undone.")) return;
    await api.del(`/api/flights/${flightId}`);
    onSaved(false);
  };

  const total = Number(d.flight_time || 0) || Number(d.sim_time || 0);
  const quick = (k: string) => (
    <button type="button" className="link small" onClick={() => set(k, total ? String(total) : "")}>all</button>
  );

  return (
    <form className="card form" onSubmit={(e) => { e.preventDefault(); save(false); }}>
      <div className="page-head">
        <h1>{flightId ? "Edit entry" : "New entry"}</h1>
        <button type="button" className="ghost" onClick={onCancel}>← Back to {backLabel()}</button>
      </div>
      {errors.length > 0 && (
        <div className="alert">
          <ul>{errors.map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      )}

      <datalist id="places">{meta.places.map((p) => <option key={p.code} value={p.code}>{p.name ?? ""}</option>)}</datalist>
      <datalist id="regs">{meta.registrations.map((r) => <option key={r.registration} value={r.registration}>{r.type_code}</option>)}</datalist>
      <datalist id="types">{meta.types.map((t) => <option key={t.code} value={t.code}>{t.name ?? ""}</option>)}</datalist>
      <datalist id="names">{meta.names.map((n) => <option key={n} value={n} />)}</datalist>
      <datalist id="devices">{meta.sim_devices.map((n) => <option key={n} value={n} />)}</datalist>
      <datalist id="approaches">{meta.approach_types.map((n) => <option key={n} value={n} />)}</datalist>

      <fieldset>
        <legend>Flight</legend>
        <div className="fields">
          {field("date", "Date", { type: "date" })}
          {field("dep", "From", { list: "places", upper: true })}
          {field("arr", "To", { list: "places", upper: true })}
          {field("route", "Via (optional)", { placeholder: "e.g. OMAD|OMAA|OMAD" })}
          {field("registration", "Registration", { list: "regs", upper: true })}
          {field("type_code", "Type", { list: "types", upper: true })}
          {field("off_time", "Off block (opt.)", { type: "time" })}
          {field("on_time", "On block (opt.)", { type: "time" })}
        </div>
        <label className="check">
          <input type="checkbox" checked={!!d.is_sim} onChange={(e) => set("is_sim", e.target.checked)} />
          Simulator session
        </label>
        {d.is_sim && (
          <div className="fields">
            {field("sim_device", "Device", { list: "devices" })}
            <label>
              <span>Level</span>
              <select value={String(d.sim_level ?? "")} onChange={(e) => set("sim_level", e.target.value)}>
                <option value="">Other / not qualified</option>
                <option value="D">Level D (counts as flight time)</option>
              </select>
            </label>
            {hours("sim_time", "Sim time")}
          </div>
        )}
      </fieldset>

      <fieldset>
        <legend>Time</legend>
        <div className="fields">
          {hours("flight_time", "Flight time")}
          <label>
            <span>Role</span>
            <select value={String(d.role ?? "")} onChange={(e) => set("role", e.target.value)}>
              <option value="">—</option>
              {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </select>
          </label>
          <label>
            <span>PF / PM</span>
            <select value={String(d.pf_pm ?? "")} onChange={(e) => set("pf_pm", e.target.value)}>
              <option value="">—</option>
              <option value="PF">PF</option>
              <option value="PM">PM</option>
            </select>
          </label>
        </div>
        <div className="fields">
          <label><span>Night {quick("night")}</span>
            <input type="number" step="0.1" min={0} value={String(d.night ?? "")} onChange={(e) => set("night", e.target.value)} /></label>
          <label><span>IFR actual {quick("ifr_actual")}</span>
            <input type="number" step="0.1" min={0} value={String(d.ifr_actual ?? "")} onChange={(e) => set("ifr_actual", e.target.value)} /></label>
          {hours("ifr_sim", "IFR simulated")}
          <label><span>Multi-pilot {quick("multi_pilot")}</span>
            <input type="number" step="0.1" min={0} value={String(d.multi_pilot ?? "")} onChange={(e) => set("multi_pilot", e.target.value)} /></label>
          {hours("xc", "Cross-country")}
          {hours("instructor", "Instructor")}
          {hours("examiner", "Examiner")}
        </div>
      </fieldset>

      <fieldset>
        <legend>Landings &amp; approaches</legend>
        <div className="fields">
          {count("ldg_day", "Day landings")}
          {count("ldg_night", "Night landings")}
          {count("to_day", "Day take-offs")}
          {count("to_night", "Night take-offs")}
          {field("approach_type", "Approach type", { list: "approaches" })}
          {count("approaches", "Approaches")}
        </div>
      </fieldset>

      <fieldset>
        <legend>
          User-defined fields
          <button type="button" className="link legend-action" onClick={() => setManaging(true)}>Manage fields…</button>
        </legend>
        {meta.custom_fields.length ? (
          <div className="fields">
            {meta.custom_fields.map((f) => f.kind === "hours" ? (
              <label key={f.slot}><span>{f.label} {quick(f.slot)}</span>
                <input type="number" step="0.1" min={0} value={String(d[f.slot] ?? "")}
                  onChange={(e) => set(f.slot, e.target.value)} /></label>
            ) : (
              <label key={f.slot}><span>{f.label}</span>
                <input type="number" step="1" min={0} value={String(d[f.slot] ?? "")}
                  onChange={(e) => set(f.slot, e.target.value)} /></label>
            ))}
          </div>
        ) : <p className="muted small">No user-defined fields. Use “Manage fields…” to add up to five hours and five number fields.</p>}
      </fieldset>
      {managing && <CustomFieldsDialog onClose={() => setManaging(false)} onChanged={onMetaChange} />}

      <fieldset>
        <legend>Crew &amp; remarks</legend>
        <div className="fields">
          {field("name_pic", "PIC name", { list: "names" })}
          {field("name_copilot", "Co-pilot", { list: "names" })}
          {field("name_instructor", "Instructor", { list: "names" })}
          {field("name_examiner", "Examiner", { list: "names" })}
          {field("name_student", "Student", { list: "names" })}
          {field("tags", "Tags", { placeholder: "e.g. NVG|OFFSHORE" })}
          {field("remarks", "Remarks", { wide: true })}
        </div>
      </fieldset>

      <div className="actions">
        <button type="submit" className="primary" disabled={saving}>{flightId ? "Save" : "Save entry"}</button>
        {!flightId && <button type="button" disabled={saving} onClick={() => save(true)}>Save &amp; add another</button>}
        <button type="button" className="ghost" onClick={onCancel}>Cancel</button>
        {flightId && <button type="button" className="danger" onClick={remove}>Delete</button>}
      </div>
    </form>
  );
}
