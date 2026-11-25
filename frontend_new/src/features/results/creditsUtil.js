// WAVE 3 PART 1B - small helpers for the CBCS results pages.
export const num = (v) => (v === null || v === undefined || v === "" ? "—" : String(Number(v)));

export const errorText = (err, fallback) => {
  const d = err?.response?.data;
  return typeof d?.detail === "string" ? d.detail : fallback;
};

// grade from marks with one regulation rule (preview only - the server grades again on save)
export function previewGrade(rule, { internal, end, total, maxMarks, hand }) {
  if (!rule) return null;
  const grades = rule.grades || [];
  const fail = grades.find((g) => g.outcome === "fail");
  if (hand) {
    const g = grades.find((x) => x.code === hand);
    return g ? { grade: g.code, pass: false, note: g.outcome === "excluded" ? "not counted" : "arrear" } : null;
  }
  const hasI = internal !== "" && internal != null;
  const hasE = end !== "" && end != null;
  const split = hasI || hasE;
  if (split && !(hasI && hasE)) return { grade: "…", pass: null, note: "both marks needed" };
  let t;
  let mx;
  if (split) {
    const i = Number(internal);
    const e = Number(end);
    if (i < 0 || i > rule.internal_max) return { grade: "!", pass: null, note: `internal 0–${rule.internal_max}` };
    if (e < 0 || e > rule.end_max) return { grade: "!", pass: null, note: `end-sem 0–${rule.end_max}` };
    t = i + e;
    mx = rule.internal_max + rule.end_max;
  } else if (total !== "" && total != null) {
    t = Number(total);
    mx = Number(maxMarks) || rule.internal_max + rule.end_max;
  } else {
    return null;
  }
  const pct = (t * 100) / mx;
  let ok = pct >= rule.min_total_pct;
  if (split && rule.end_max) ok = ok && (Number(end) * 100) / rule.end_max >= rule.min_end_pct;
  if (!ok) return { grade: fail?.code || "RA", pass: false, note: "arrear" };
  const band = grades.filter((g) => g.outcome === "pass")
    .sort((a, b) => b.min_mark - a.min_mark).find((g) => pct >= g.min_mark);
  return band ? { grade: band.code, pass: true, total: t } : null;
}
