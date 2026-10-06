import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api, ApiError, CustomField, fmtHours, MAX_CUSTOM } from "../api";

const KINDS: { kind: "hours" | "number"; title: string; hint: string }[] = [
  { kind: "hours", title: "Hours fields", hint: "Logged in decimal hours, e.g. NVG, hoist time, mountain flying." },
  { kind: "number", title: "Number fields", hint: "Whole numbers, e.g. ship landings, hoist cycles, confined areas." },
];

function FieldRow({ f, onChanged, onError }: { f: CustomField; onChanged: () => void; onError: (e: string) => void }) {
  const [label, setLabel] = useState(f.label);
  const dirty = label.trim() !== f.label;
  const fail = (e: unknown) => onError(e instanceof ApiError ? e.errors.join(" ") : String(e));
  const rename = () => api.put(`/api/custom-fields/${f.slot}`, { label }).then(onChanged).catch(fail);
  const remove = async () => {
    const used = f.entries
      ? `\n\n${f.entries} entr${f.entries === 1 ? "y has" : "ies have"} a value in it (total ${f.kind === "hours" ? `${fmtHours(f.total)} h` : f.total}). Those values will be erased.`
      : "";
    if (!confirm(`Remove the field "${f.label}"?${used}\n\nThis cannot be undone (except from a backup).`)) return;
    api.del(`/api/custom-fields/${f.slot}`).then(onChanged).catch(fail);
  };
  return (
    <li className="cf-row">
      <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={30}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (dirty) rename(); } }} aria-label="Field name" />
      <span className="muted small nowrap">
        {f.entries ? `${f.entries} entries · ${f.kind === "hours" ? `${fmtHours(f.total)} h` : f.total}` : "not used yet"}
      </span>
      {dirty ? <button type="button" className="primary small" onClick={rename}>Save</button>
        : <button type="button" className="small danger-text" onClick={remove}>Remove</button>}
    </li>
  );
}

export default function CustomFieldsDialog({ onClose, onChanged }: { onClose: () => void; onChanged: () => void }) {
  const [fields, setFields] = useState<CustomField[]>([]);
  const [draft, setDraft] = useState<Record<string, string>>({ hours: "", number: "" });
  const [error, setError] = useState("");

  const load = () => api.get<CustomField[]>("/api/custom-fields").then(setFields);
  useEffect(() => { load(); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const changed = () => { setError(""); load(); onChanged(); };
  const add = (kind: "hours" | "number") =>
    api.post("/api/custom-fields", { label: draft[kind], kind })
      .then(() => { setDraft({ ...draft, [kind]: "" }); changed(); })
      .catch((e) => setError(e instanceof ApiError ? e.errors.join(" ") : String(e)));

  // Rendered at <body> level: the dialog opens from inside the entry form and must not submit it
  return createPortal(
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal card" role="dialog" aria-modal="true" aria-labelledby="cf-title">
        <div className="page-head">
          <h2 id="cf-title">User-defined fields</h2>
          <button type="button" className="ghost" onClick={onClose}>Done</button>
        </div>
        <p className="muted small">Up to {MAX_CUSTOM} of each kind. They appear in their own section of the entry form,
          as columns and filters in Reports, and in the dashboard's last-90-days table.</p>
        {error && <div className="alert">{error}</div>}
        <div className="grid-2 tight">
          {KINDS.map(({ kind, title, hint }) => {
            const mine = fields.filter((f) => f.kind === kind);
            const full = mine.length >= MAX_CUSTOM;
            return (
              <section key={kind}>
                <h3>{title} <span className="muted">({mine.length}/{MAX_CUSTOM})</span></h3>
                <ul className="cf-list">
                  {mine.map((f) => <FieldRow key={f.slot + f.label} f={f} onChanged={changed} onError={setError} />)}
                  {!mine.length && <li className="muted small">None yet.</li>}
                </ul>
                <div className="cf-add">
                  <input placeholder={full ? `Limit of ${MAX_CUSTOM} reached` : "New field name"} disabled={full}
                    value={draft[kind]} maxLength={30} onChange={(e) => setDraft({ ...draft, [kind]: e.target.value })}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (draft[kind].trim()) add(kind); } }} />
                  <button type="button" disabled={full || !draft[kind].trim()} onClick={() => add(kind)}>Add</button>
                </div>
                <p className="muted small">{hint}</p>
              </section>
            );
          })}
        </div>
      </div>
    </div>,
    document.body,
  );
}
