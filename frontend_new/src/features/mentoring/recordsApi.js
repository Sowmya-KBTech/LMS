// WAVE 1 - mentoring records (mentoring & guidance by category)
import API from "../../api";

export const getStudentRecords = (studentId, category) =>
  API.get("mentoring/records/", { params: { student: studentId, ...(category ? { category } : {}) } })
    .then((r) => r.data);

export const addRecord = (body) => API.post("mentoring/records/", body).then((r) => r.data);
export const updateRecord = (id, body) => API.patch(`mentoring/records/${id}/`, body).then((r) => r.data);
export const deleteRecord = (id) => API.delete(`mentoring/records/${id}/`);

export const getMyGuidance = () => API.get("mentoring/student/records/").then((r) => r.data);

export const getRecordsSummary = (params = {}) =>
  API.get("mentoring/hod/records/summary/", { params }).then((r) => r.data);

export const recordError = (err, fallback) => {
  const d = err?.response?.data;
  if (typeof d?.detail === "string") return d.detail;
  return fallback;
};

export const CATEGORY_TONE = {
  academic: "ma-blue",
  personal: "ma-purple",
  competitive: "ma-amber",
  career: "ma-green",
  other: "ma-grey",
};

export const showDate = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
};
