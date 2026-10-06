import { useCallback, useEffect, useState } from "react";
import { api, Meta } from "./api";
import Dashboard from "./pages/Dashboard";
import Flights from "./pages/Flights";
import Reports from "./pages/Reports";
import Types from "./pages/Types";
import Places from "./pages/Places";
import People from "./pages/People";
import Data from "./pages/Data";

const PAGES = [
  { path: "dashboard", label: "Dashboard" },
  { path: "flights", label: "Flights" },
  { path: "reports", label: "Reports" },
  { path: "people", label: "People" },
  { path: "types", label: "Aircraft types" },
  { path: "places", label: "Places" },
  { path: "data", label: "Import & backup" },
];

const current = () => window.location.hash.replace(/^#\/?/, "").split("/")[0] || "dashboard";

export default function App() {
  const [page, setPage] = useState(current);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState("");
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || "dark");

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch { /* storage unavailable: applies to this visit only */ }
    setTheme(next);
  };

  const reloadMeta = useCallback(() => {
    api.get<Meta>("/api/meta").then(setMeta).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    reloadMeta();
    const onHash = () => setPage(current());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [reloadMeta]);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>
            ✈
          </span>
          Logbook
        </div>
        <nav>
          {PAGES.map((p) => (
            <a key={p.path} href={`#/${p.path}`} className={page === p.path ? "active" : ""}>
              {p.label}
            </a>
          ))}
        </nav>
        <button className="theme-toggle" onClick={toggleTheme} title="Switch between dark and light mode">
          {theme === "dark" ? "☀ Light" : "☾ Dark"}
        </button>
      </header>
      <main>
        {error && <div className="alert">Cannot reach the logbook server: {error}</div>}
        {meta && page === "dashboard" && <Dashboard />}
        {meta && page === "flights" && <Flights meta={meta} onChange={reloadMeta} />}
        {meta && page === "reports" && <Reports meta={meta} />}
        {meta && page === "people" && <People />}
        {meta && page === "types" && <Types meta={meta} onChange={reloadMeta} />}
        {meta && page === "places" && <Places onChange={reloadMeta} />}
        {meta && page === "data" && <Data onChange={reloadMeta} />}
      </main>
    </div>
  );
}
