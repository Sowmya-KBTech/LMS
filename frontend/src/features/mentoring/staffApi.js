// frontend/src/features/mentoring/staffApi.js
import API from "../../api";

const B = "mentoring/staff/";

const qs = (p = {}) => {
  const q = new URLSearchParams();
  Object.entries(p).forEach(([k, v]) => {
    if (v !== "" && v !== null && v !== undefined && v !== "all") q.set(k, v);
  });
  const s = q.toString();
  return s ? `?${s}` : "";
};

// ================= READ =================
export const getMyMentees = (p) => API.get(`${B}my-mentees/${qs(p)}`).then((r) => r.data);
export const getMenteeDetail = (id, p) =>
  API.get(`${B}students/${id}/${qs(p)}`).then((r) => r.data);
export const getConversations = (p) => API.get(`${B}messages/${qs(p)}`).then((r) => r.data);
export const getThread = (id, p) => API.get(`${B}messages/${id}/${qs(p)}`).then((r) => r.data);
export const getGroups = (p) => API.get(`${B}groups/${qs(p)}`).then((r) => r.data);

// ================= WRITE =================
export const sendMessage = (id, text) =>
  API.post(`${B}messages/${id}/`, { text }).then((r) => r.data);
export const broadcast = (group, text) =>
  API.post(`${B}broadcast/`, { group, text }).then((r) => r.data);

// ================= HELPERS =================
export const gradeClass = (g) =>
  ({ A: "ma-green", B: "ma-blue", C: "ma-amber" }[g] || "ma-grey");

export const yearLabel = (y) => ({ 1: "I", 2: "II", 3: "III", 4: "IV" }[y] || y || "—");

export const attClass = (a) =>
  a == null ? "ma-grey" : a < 75 ? "ma-red" : a < 80 ? "ma-amber" : "ma-green";

export const when = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
};

export const errorText = (err, fallback = "Something went wrong.") => {
  const d = err?.response?.data;
  if (!d) return fallback;
  if (typeof d === "string") return d;
  if (d.detail) return d.detail;
  const first = Object.values(d)[0];
  if (Array.isArray(first)) return first[0];
  if (typeof first === "string") return first;
  return fallback;
};

// ================= CHANGE REQUESTS (class advisor) =================
// bucket: "waiting" (default) | "forwarded" | "resolved"
export const getStaffChangeRequests = (params) => {
  const q = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== "" && v !== null && v !== undefined && v !== "all") q.set(k, v);
  });
  const s = q.toString();
  return API.get(`mentoring/staff/change-requests/${s ? `?${s}` : ""}`)
    .then((r) => r.data);
};

export const getStaffChangeRequest = (id) =>
  API.get(`mentoring/staff/change-requests/${id}/`).then((r) => r.data);

/** action: "forward" | "resolve". A note is required either way. */
export const actOnChangeRequest = (id, body) =>
  API.post(`mentoring/staff/change-requests/${id}/act/`, body).then((r) => r.data);

// ================= MY REQUESTS (as a mentor) =================
export const getMyRaisedRequests = () =>
  API.get("mentoring/staff/my-change-requests/").then((r) => r.data);

/** {student_id, reason, detail}. 409 if that student already has one open. */
export const raiseMenteeRequest = (body) =>
  API.post("mentoring/staff/my-change-requests/", body).then((r) => r.data);

export const withdrawMyRequest = (id) =>
  API.post(`mentoring/staff/my-change-requests/${id}/withdraw/`).then((r) => r.data);