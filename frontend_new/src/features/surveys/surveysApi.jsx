// WAVE 2 - surveys
import { useState } from "react";
import API from "../../api";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";

export const svApi = {
  list: () => API.get("surveys/manage/").then((r) => r.data),
  get: (id) => API.get(`surveys/manage/${id}/`).then((r) => r.data),
  create: (body) => API.post("surveys/manage/", body).then((r) => r.data),
  update: (id, body) => API.put(`surveys/manage/${id}/`, body).then((r) => r.data),
  remove: (id) => API.delete(`surveys/manage/${id}/`),
  publish: (id) => API.post(`surveys/manage/${id}/publish/`).then((r) => r.data),
  close: (id) => API.post(`surveys/manage/${id}/close/`).then((r) => r.data),
  results: (id) => API.get(`surveys/manage/${id}/results/`).then((r) => r.data),
  options: () => API.get("surveys/options/").then((r) => r.data),
  templates: () => API.get("surveys/templates/").then((r) => r.data),
  mine: () => API.get("surveys/my/").then((r) => r.data),
  mineOne: (id) => API.get(`surveys/my/${id}/`).then((r) => r.data),
  submit: (id, answers) => API.post(`surveys/my/${id}/submit/`, { answers }).then((r) => r.data),
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

export const KINDS = [
  { value: "rating", label: "Rating 1–5" },
  { value: "choice", label: "One choice" },
  { value: "multi", label: "Several choices" },
  { value: "text", label: "Written answer" },
];

export const RATING_WORDS = ["", "Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree"];

export function statusPill(s) {
  if (s.status === "draft") return { tone: "", text: "Draft" };
  if (s.status === "closed" || s.ended) return { tone: "", text: "Closed" };
  if (!s.accepting) return { tone: "info", text: `Opens ${fmtDate(s.start_date)}` };
  return { tone: "ok", text: "Open" };
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
            <div className="header-box sv-header">
              <div>
                <h1>{title}</h1>
                {subtitle && <p>{subtitle}</p>}
              </div>
              {actions && <div className="sv-header-actions no-print">{actions}</div>}
            </div>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}
