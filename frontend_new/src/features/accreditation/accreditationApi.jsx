// WAVE 2 - accreditation (NAAC / NBA) reports
import { useState } from "react";
import API from "../../api";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";

const clean = (params) => Object.fromEntries(Object.entries(params).filter(([, v]) => v !== "" && v != null));

export const acApi = {
  list: (params) => API.get("accreditation/reports/", { params: clean(params) }).then((r) => r.data),
  one: (key, params) => API.get(`accreditation/reports/${key}/`, { params: clean(params) }).then((r) => r.data),
  // the file needs the sign-in token, so it is fetched like any API call and then saved
  // name is built here: the browser can't read the server's file name across origins
  excel: async (key, params, name) => {
    const r = await API.get(`accreditation/reports/${key}/excel/`, { params: clean(params), responseType: "blob" });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};

export const errorText = (err, fallback) => {
  const d = err?.response?.data;
  return typeof d?.detail === "string" ? d.detail : fallback;
};

export const fmtDate = (iso) => {
  if (!iso) return "";
  const [y, m, d] = String(iso).slice(0, 10).split("-");
  return `${d}-${m}-${y}`;
};

export function cellText(value, type) {
  if (value == null || value === "") return "—";
  if (type === "pct") return `${value}%`;
  return String(value);
}

export function Shell({ title, subtitle, actions, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="header-box ac-header">
              <div>
                <h1>{title}</h1>
                {subtitle && <p>{subtitle}</p>}
              </div>
              {actions && <div className="ac-actions no-print">{actions}</div>}
            </div>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

// Year + department pickers, shared by both pages. Values live in the URL (?year=&department=).
export function Pickers({ meta, year, department, onChange }) {
  if (!meta) return null;
  return (
    <div className="ac-pickers no-print">
      <label>Academic year
        <select value={year || meta.year} onChange={(e) => onChange({ year: e.target.value, department })}>
          {meta.years.map((y) => <option key={y.year} value={y.year}>{y.label}</option>)}
        </select>
      </label>
      <label>Department
        <select value={department || ""} disabled={!meta.college_wide}
          onChange={(e) => onChange({ year: year || meta.year, department: e.target.value })}>
          {meta.college_wide && <option value="">All departments</option>}
          {meta.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </label>
      <span className="ac-range">{fmtDate(meta.from)} – {fmtDate(meta.to)}</span>
    </div>
  );
}
