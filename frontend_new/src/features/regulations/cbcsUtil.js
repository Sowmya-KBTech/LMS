// WAVE 3 PART 1A - small helpers for the CBCS pages.
export const errorText = (err, fallback) => {
  const d = err?.response?.data;
  if (typeof d?.detail === "string") return d.detail;
  if (d && typeof d === "object") {
    const first = Object.values(d)[0];
    if (Array.isArray(first) && typeof first[0] === "string") return first[0];
  }
  return fallback;
};

// 4 -> "4", 1.5 -> "1.5", 50 -> "50"
export const num = (v) => (v === null || v === undefined || v === "" ? "" : String(Number(v)));
