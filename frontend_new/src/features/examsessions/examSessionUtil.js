// WAVE 3 PART 2 - small helpers for the exam session pages.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// "2026-12-08" -> "8 Dec 2026"
export function longDate(iso) {
  if (!iso) return "—";
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

// "2026-12-08" -> "Tue 8 Dec"
export function dayLabel(iso) {
  if (!iso) return "—";
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  return `${DAYS[new Date(y, m - 1, d).getDay()]} ${d} ${MONTHS[m - 1]}`;
}

// "2026-12-08" -> "08-12-2026" (what the date inputs show)
export function dmy(iso) {
  if (!iso) return "";
  return String(iso).slice(0, 10).split("-").reverse().join("-");
}

export function rupees(v) {
  const n = Number(v || 0);
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export function errorText(err, fallback) {
  const d = err?.response?.data;
  if (typeof d?.detail === "string") return d.detail;
  if (Array.isArray(d?.detail)) return d.detail.join(" ");
  return fallback;
}

export const WINDOW_LABEL = {
  not_required: { text: "No registration", tone: "grey" },
  not_open: { text: "Registration not open yet", tone: "grey" },
  open: { text: "Registration open", tone: "ok" },
  late: { text: "Late registration", tone: "warn" },
  closed: { text: "Registration closed", tone: "grey" },
};

export const plural = (n, word, many) => `${n} ${n === 1 ? word : many || `${word}s`}`;
