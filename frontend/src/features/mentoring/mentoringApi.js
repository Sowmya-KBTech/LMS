// frontend/src/features/mentoring/mentoringApi.js
import API from "../../api";

const BASE = "mentoring/hod/";

// Turns { year: 3, band: "" } into "?year=3" — blank values are dropped so the
// backend never receives band="" and filters everything out by mistake.
const qs = (params = {}) => {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== "" && v !== null && v !== undefined && v !== "all") {
      q.set(k, v);
    }
  });
  const s = q.toString();
  return s ? `?${s}` : "";
};

// ================= READ =================
export const getOptions = (params) =>
  API.get(`${BASE}options/${qs(params)}`).then((r) => r.data);

export const getDashboard = (params) =>
  API.get(`${BASE}dashboard/${qs(params)}`).then((r) => r.data);

export const getAllocations = (params) =>
  API.get(`${BASE}allocations/${qs(params)}`).then((r) => r.data);

export const getProposals = (params) =>
  API.get(`${BASE}proposals/${qs(params)}`).then((r) => r.data);

export const getMentor = (mentorId, params) =>
  API.get(`${BASE}mentors/${mentorId}/${qs(params)}`).then((r) => r.data);

export const getHistory = (params) =>
  API.get(`${BASE}history/${qs(params)}`).then((r) => r.data);

export const getSettings = (params) =>
  API.get(`${BASE}settings/${qs(params)}`).then((r) => r.data);

// best fit for one student, or the whole-pool preview when studentId is omitted
export const getSuggestion = (studentId, params) =>
  API.get(`${BASE}suggest/${qs({ ...params, student: studentId })}`).then(
    (r) => r.data
  );

export const getSplitPreview = (params) =>
  API.get(`${BASE}suggest/${qs(params)}`).then((r) => r.data);

// ================= CHANGE REQUESTS =================
// bucket: "waiting" (default) | "advisor" | "decided"
export const getChangeRequests = (params) =>
  API.get(`${BASE}change-requests/${qs(params)}`).then((r) => r.data);

export const getChangeRequest = (requestId, params) =>
  API.get(`${BASE}change-requests/${requestId}/${qs(params)}`).then((r) => r.data);

/**
 * Approve or reject. Same 409 contract as assignMentor — over capacity is a
 * WARNING, so call again with override:true once the user confirms.
 */
export const decideChangeRequest = (requestId, body) =>
  API.post(`${BASE}change-requests/${requestId}/decide/`, body).then((r) => r.data);


// ================= WRITE =================
/**
 * Assign or reassign. The backend answers 409 when the mentor would go over
 * capacity — that is a WARNING, not a failure. Call again with override:true
 * once the user confirms.
 */
export const assignMentor = (body) =>
  API.post(`${BASE}assign/`, body).then((r) => r.data);

export const autoDistribute = (body) =>
  API.post(`${BASE}auto-distribute/`, body || {}).then((r) => r.data);

export const decideProposals = (body) =>
  API.post(`${BASE}decide-proposals/`, body).then((r) => r.data);

export const removeAllocation = (allocationId, body) =>
  API.post(`${BASE}allocations/${allocationId}/remove/`, body || {}).then(
    (r) => r.data
  );

export const saveSettings = (body) =>
  API.patch(`${BASE}settings/`, body).then((r) => r.data);

// ================= HELPERS =================
export const bandClass = (band) =>
  ({ A: "ma-green", B: "ma-blue", C: "ma-amber" }[band] || "ma-grey");

export const statusPill = (status) =>
  ({
    active: { cls: "ma-green", label: "Active" },
    pending: { cls: "ma-amber", label: "Awaiting approval" },
    none: { cls: "ma-grey", label: "No mentor" },
    closed: { cls: "ma-grey", label: "Closed" },
    rejected: { cls: "ma-red", label: "Rejected" },
  }[status] || { cls: "ma-grey", label: status || "—" });

export const yearLabel = (y) =>
  ({ 1: "I", 2: "II", 3: "III", 4: "IV" }[y] || y || "—");

// Pill for a change request status.
export const requestPill = (status) =>
  ({
    advisor: { cls: "ma-amber", label: "With the class advisor" },
    hod: { cls: "ma-blue", label: "Waiting on you" },
    approved: { cls: "ma-green", label: "Approved" },
    rejected: { cls: "ma-red", label: "Rejected" },
    resolved: { cls: "ma-grey", label: "Resolved by the advisor" },
    withdrawn: { cls: "ma-grey", label: "Withdrawn" },
  }[status] || { cls: "ma-grey", label: status || "—" });

// "4 days old" for the queue. Age is what makes a stale request visible.
export const ageText = (iso) => {
  if (!iso) return "";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  return `${days} days old`;
};

// "2026-2027" -> "2026–2027" (en dash, matches the rest of the UI)
export const prettyYear = (ay) => (ay || "").replace("-", "\u2013");

// Pulls a readable message out of any DRF error shape.
export const errorText = (err, fallback = "Something went wrong.") => {
  const d = err?.response?.data;
  if (!d) return fallback;
  if (typeof d === "string") return d;
  if (d.detail) return d.detail;
  if (d.message) return d.message;
  const first = Object.values(d)[0];
  if (Array.isArray(first)) return first[0];
  if (typeof first === "string") return first;
  return fallback;
};