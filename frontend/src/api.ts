export type Kind = "date" | "text" | "duration" | "count" | "choice" | "flag";

export interface Flight {
  id?: number;
  date: string;
  dep: string | null;
  arr: string | null;
  route: string | null;
  type_code: string;
  registration: string | null;
  is_sim: boolean;
  sim_device: string | null;
  sim_level: string | null;
  off_time: string | null;
  on_time: string | null;
  flight_time: number;
  sim_time: number;
  pic: number;
  picus: number;
  sic: number;
  dual: number;
  instructor: number;
  examiner: number;
  night: number;
  ifr_actual: number;
  ifr_sim: number;
  ifr?: number;
  xc: number;
  multi_pilot: number;
  ldg_day: number;
  ldg_night: number;
  to_day: number;
  to_night: number;
  approach_type: string | null;
  approaches: number;
  pf_pm: "PF" | "PM" | null;
  name_pic: string | null;
  name_copilot: string | null;
  name_student: string | null;
  name_instructor: string | null;
  name_examiner: string | null;
  remarks: string | null;
  tags: string | null;
  // User-defined fields: hours slots uh1-uh5, number slots un1-un5
  uh1: number; uh2: number; uh3: number; uh4: number; uh5: number;
  un1: number; un2: number; un3: number; un4: number; un5: number;
}

export interface CustomField {
  slot: string;
  label: string;
  kind: "hours" | "number";
  entries?: number;
  total?: number;
}
export const MAX_CUSTOM = 5;

export interface AircraftType {
  code: string;
  name: string | null;
  category: "helicopter" | "aeroplane" | "other";
  engines: "single" | "multi" | null;
  power: "piston" | "turbine" | null;
  multi_pilot: number;
}

export interface Place {
  code: string;
  name: string | null;
  kind: string | null;
  lat: number | null;
  lon: number | null;
  notes: string | null;
  flights?: number;
  last_visit?: string | null;
}

export interface Option { key: string; label: string; kind?: Kind }

export interface Meta {
  fields: Option[];
  metrics: Option[];
  dimensions: Option[];
  roles: Option[];
  types: AircraftType[];
  registrations: { registration: string; type_code: string; is_sim: number; n: number }[];
  places: Place[];
  names: string[];
  sim_devices: string[];
  approach_types: string[];
  custom_fields: CustomField[];
}

export interface ReportFilters {
  date_from?: string;
  date_to?: string;
  type_codes?: string[];
  registrations?: string[];
  categories?: string[];
  kind?: "" | "aircraft" | "sim" | "flight_time";
  roles?: string[];
  conditions?: string[];
  pf_pm?: "" | "PF" | "PM";
  place?: string;
  text?: string;
}

export interface ReportSpec {
  title?: string;
  mode: "summary" | "detail";
  filters: ReportFilters;
  group_by: string[];
  columns: string[];
}

export interface ReportResult {
  headers: { key: string; label: string; kind: Kind }[];
  rows: (string | number | null)[][];
  totals: (string | number | null)[];
}

export interface Summary {
  entries: number;
  first: string | null;
  last: string | null;
  as_of: string;
  totals: Record<string, number>;
  periods: { label: string; hours: number }[];
  currency: { label: string; kind: "hours" | "number"; last_90: number; last: string | null }[];
  by_type: { type_code: string; hours: number; last: string }[];
}

export class ApiError extends Error {
  constructor(public errors: string[]) {
    super(errors.join(" "));
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const res = await fetch(url, init);
  if (!res.ok) {
    let errors = [`${res.status} ${res.statusText}`];
    try {
      const data = await res.json();
      if (data?.detail?.errors) errors = data.detail.errors;
      else if (typeof data?.detail === "string") errors = [data.detail];
    } catch {
      /* not JSON */
    }
    throw new ApiError(errors);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  post: <T>(url: string, body?: unknown) => request<T>("POST", url, body),
  put: <T>(url: string, body: unknown) => request<T>("PUT", url, body),
  del: (url: string) => request<void>("DELETE", url),
  async download(url: string, body: unknown, filename: string) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new ApiError([`Export failed (${res.status})`]);
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  },
};

export const fmtHours = (h: number | null | undefined) =>
  h === null || h === undefined ? "" : h.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export const fmtCell = (v: string | number | null, kind: Kind) =>
  v === null || v === undefined ? "" : kind === "duration" && typeof v === "number" ? fmtHours(v) :
    typeof v === "number" ? v.toLocaleString() : String(v);

export const today = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};

/** Open a flight, remembering the current page so closing it returns here. */
export const openFlight = (id: number) => {
  const back = window.location.hash || "#/flights";
  window.location.hash = `#/flights/${id}?back=${encodeURIComponent(back)}`;
};

/** Where to go when a flight is closed: the page it was opened from, else the flight list. */
export const backTarget = () => {
  const query = window.location.hash.split("?")[1] ?? "";
  const back = new URLSearchParams(query).get("back");
  return back && back.startsWith("#/") ? back : "#/flights";
};

export const backLabel = () => {
  const page = backTarget().replace(/^#\//, "").split(/[/?]/)[0];
  return { people: "People", reports: "Reports", dashboard: "Dashboard" }[page] ?? "Flights";
};
