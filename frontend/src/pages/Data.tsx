import { useState } from "react";
import { api, ApiError } from "../api";

interface ImportResult {
  read: number; imported: number; corrected: number; split: number; deleted: number;
  invalid: { row: number; date: string; errors: string[] }[];
}

export default function Data({ onChange }: { onChange: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [fixes, setFixes] = useState<File | null>(null);
  const [replace, setReplace] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    if (!file) return;
    setBusy(true); setErrors([]); setResult(null);
    const form = new FormData();
    form.append("export", file);
    if (fixes) form.append("corrections", fixes);
    form.append("replace", String(replace));
    try {
      setResult(await api.post<ImportResult>("/api/import", form));
      onChange();
    } catch (e) {
      setErrors(e instanceof ApiError ? e.errors : [String(e)]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="page-head"><h1>Import &amp; backup</h1></div>
      <div className="grid-2">
        <section className="card">
          <h2>Import FLYLOG export</h2>
          <p className="muted">Imports the Excel export and applies your corrections file. If any entry fails the
            logbook rules, nothing is imported and the problems are listed.</p>
          <label className="stack"><span>FLYLOG export (.xlsx)</span>
            <input type="file" accept=".xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
          <label className="stack"><span>Corrections file (.json, optional)</span>
            <input type="file" accept=".json" onChange={(e) => setFixes(e.target.files?.[0] ?? null)} /></label>
          <label className="check">
            <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
            Replace a previous import (entries you added in the app are kept)
          </label>
          <div className="actions"><button className="primary" disabled={!file || busy} onClick={run}>{busy ? "Importing…" : "Import"}</button></div>
          {errors.length > 0 && <div className="alert">{errors.join(" ")}</div>}
          {result && (
            <div className={result.invalid.length ? "alert" : "ok"}>
              {result.invalid.length ? (
                <>
                  <strong>{result.invalid.length} entries break the rules — nothing imported:</strong>
                  <ul>{result.invalid.slice(0, 50).map((p) => <li key={p.row}>Row {p.row} ({p.date}): {p.errors.join("; ")}</li>)}</ul>
                </>
              ) : (
                <>Read {result.read} rows → imported {result.imported} entries ({result.corrected} corrected,
                  {" "}{result.split} split, {result.deleted} deleted).</>
              )}
            </div>
          )}
        </section>
        <section className="card">
          <h2>Backup</h2>
          <p className="muted">Your logbook is a single file on this computer (<code>data/logbook.db</code>).
            Download a copy regularly and keep it somewhere safe.</p>
          <div className="actions"><a className="button primary" href="/api/backup">Download backup</a></div>
        </section>
      </div>
    </>
  );
}
