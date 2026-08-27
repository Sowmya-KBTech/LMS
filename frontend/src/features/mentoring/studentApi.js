// frontend/src/features/mentoring/studentApi.js
import API from "../../api";

const B = "mentoring/student/";

// ================= READ =================
export const getMyMentor = () => API.get(`${B}my-mentor/`).then((r) => r.data);
export const getThread = () => API.get(`${B}messages/`).then((r) => r.data);
export const getAnnouncements = () => API.get(`${B}announcements/`).then((r) => r.data);

// ================= WRITE =================
export const sendMessage = (text) =>
  API.post(`${B}messages/`, { text }).then((r) => r.data);

// ================= CHANGE REQUEST =================
export const getChangeRequest = () =>
  API.get(`${B}change-request/`).then((r) => r.data);

/** Raise one. Backend answers 409 if a request is already in progress. */
export const raiseChangeRequest = (body) =>
  API.post(`${B}change-request/`, body).then((r) => r.data);

export const withdrawChangeRequest = (id) =>
  API.post(`${B}change-request/${id}/withdraw/`).then((r) => r.data);

// ================= HELPERS =================
export const yearLabel = (y) => ({ 1: "I", 2: "II", 3: "III", 4: "IV" }[y] || y || "—");

export const prettyYear = (ay) => (ay || "").replace("-", "\u2013");

export const when = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (d.toDateString() === new Date().toDateString())
    return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
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