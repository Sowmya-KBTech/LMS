// WAVE 1 - progress reports and rank lists
import API from "../../api";

export const getReportClasses = () => API.get("reports/classes/").then((r) => r.data);
export const getRankList = (course, year, semester) =>
  API.get("reports/rank-list/", { params: { course, year, semester } }).then((r) => r.data);
export const getProgressReport = (studentId) =>
  API.get(studentId ? `reports/progress/${studentId}/` : "reports/progress/me/").then((r) => r.data);
export const getCollege = () => API.get("college/").then((r) => r.data).catch(() => ({}));

export const errorText = (err, fallback) => {
  const d = err?.response?.data;
  return typeof d?.detail === "string" ? d.detail : fallback;
};

export const pctTone = (p) => (p >= 75 ? "ok" : p >= 60 ? "warn" : "bad");
export const roman = (y) => ({ 1: "I", 2: "II", 3: "III", 4: "IV" }[y] || y);
