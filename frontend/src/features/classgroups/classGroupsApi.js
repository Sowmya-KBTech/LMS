// frontend/src/features/classgroups/classGroupsApi.js
import API from "../../api";

const B = "class-groups/";

// blank values are dropped so the backend never receives kind="" and filters
// everything out by mistake
const qs = (p = {}) => {
  const q = new URLSearchParams();
  Object.entries(p).forEach(([k, v]) => {
    if (v !== "" && v !== null && v !== undefined && v !== "all") q.set(k, v);
  });
  const s = q.toString();
  return s ? `?${s}` : "";
};

// ================= READ =================
export const getMyGroups = () => API.get(B).then((r) => r.data);

export const getGroup = (id) => API.get(`${B}${id}/`).then((r) => r.data);

export const getStudents = (id, params) =>
  API.get(`${B}${id}/students/${qs(params)}`).then((r) => r.data);

export const getMessages = (id, params) =>
  API.get(`${B}${id}/messages/${qs(params)}`).then((r) => r.data);

export const getFiles = (params) =>
  API.get(`${B}files/${qs(params)}`).then((r) => r.data);

export const getSettings = (id) =>
  API.get(`${B}${id}/settings/`).then((r) => r.data);

// ================= WRITE =================
/**
 * Sends multipart because a message can carry a file.
 * type "announcement" also needs a title; the backend rejects it otherwise.
 */
export const sendMessage = (id, { text, title, file, isAnnouncement, isPinned }) => {
  const fd = new FormData();
  fd.append("message_type", isAnnouncement ? "announcement" : "text");
  if (text) fd.append("text", text);
  if (title) fd.append("title", title);
  if (file) fd.append("attachment", file);
  if (isPinned) fd.append("is_pinned", "true");
  return API.post(`${B}${id}/messages/`, fd, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data);
};

export const deleteMessage = (id, messageId) =>
  API.delete(`${B}${id}/messages/${messageId}/`).then((r) => r.data);

export const togglePin = (id, messageId) =>
  API.post(`${B}${id}/messages/${messageId}/pin/`).then((r) => r.data);

export const saveSettings = (id, body) =>
  API.patch(`${B}${id}/settings/`, body).then((r) => r.data);

// ================= HELPERS =================
export const when = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (d.toDateString() === new Date().toDateString())
    return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
};

export const dayLabel = (iso) => {
  const d = new Date(iso);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return "Today";
  const y = new Date(today);
  y.setDate(y.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return "Yesterday";
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "long" });
};

export const initials = (name) =>
  (name || "?").split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase();

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


// ================= PRIVATE 1-TO-1 =================
// These hit the chat endpoints, not class-groups/. The server decides who you
// may talk to (courses.views.message_partner_ids) and which thread a message
// belongs to — the mentor thread is not reachable from here.

export const getPrivateContacts = (kind = "students") =>
  API.get(`chat/contacts/?kind=${kind}`).then((r) => r.data);

export const getPrivateThread = (userId) =>
  API.get(`chat/with/${userId}/`).then((r) => r.data);

/** Multipart, because a private message can carry a file (10 MB max). */
export const sendPrivateMessage = (userId, { text, file }) => {
  const fd = new FormData();
  if (text) fd.append("text", text);
  if (file) fd.append("attachment", file);
  return API.post(`chat/with/${userId}/`, fd, {
    headers: { "Content-Type": "multipart/form-data" },
  }).then((r) => r.data);
};

export const fileSize = (bytes) => {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};