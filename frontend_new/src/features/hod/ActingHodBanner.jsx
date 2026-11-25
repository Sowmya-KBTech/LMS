// #50 ACTING HOD (Step 4): information banner for the logged-in teacher.
// It only SHOWS what the server says (users/acting-hod/me/).
// Permissions never depend on this banner.
import { useEffect, useState } from "react";
import API from "../../api";

const fmtD = (iso) => {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}-${m}-${y}`;
};

const fmtTime = (iso) =>
  new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });

const TONES = {
  green:  { bg: "#ecfdf3", fg: "#14532d", bd: "#bbf7d0" },
  violet: { bg: "#efeafe", fg: "#2B1A3F", bd: "#d9d0fb" },
  amber:  { bg: "#fffbeb", fg: "#78350f", bd: "#fde68a" },
};

const SUB = { fontSize: 13.5, marginTop: 4, opacity: 0.85 };

function Box({ tone, icon, children }) {
  const t = TONES[tone];
  return (
    <div style={{
      background: t.bg, color: t.fg, border: `1px solid ${t.bd}`,
      borderRadius: 12, padding: "12px 16px", fontSize: 15, lineHeight: 1.45,
      display: "flex", gap: 10, alignItems: "flex-start",
    }}>
      <span aria-hidden="true">{icon}</span>
      <div>{children}</div>
    </div>
  );
}

export default function ActingHodBanner({ spanAll = false }) {
  const [info, setInfo] = useState(null);

  useEffect(() => {
    let cancelled = false;
    API.get("users/acting-hod/me/")
      .then((res) => { if (!cancelled) setInfo(res.data); })
      .catch((err) => console.error("Acting HOD banner failed:", err?.response?.status));
    return () => { cancelled = true; };
  }, []);

  if (!info) return null;
  const { acting, upcoming, covered_by: cov } = info;
  const pend = info.pending_nominations || [];
  if (!acting && !upcoming && !cov && pend.length === 0) return null;

  return (
    <div style={{
      display: "flex", flexDirection: "column", gap: 10, marginBottom: 14,
      ...(spanAll ? { gridColumn: "1 / -1" } : {}),
    }}>
      {acting && (
        <Box tone="green" icon="🟢">
          <b>You are Acting HOD of {acting.department}.</b>{" "}
          {acting.started_at
            ? <>Your responsibility started on {fmtD(acting.started_at)} at {fmtTime(acting.started_at)} and ends on {fmtD(acting.end_date)}.</>
            : <>From {fmtD(acting.start_date)} to {fmtD(acting.end_date)}.</>}
          <div style={SUB}>
            Reason: {acting.reason}
            {acting.approved_by ? ` · Approved by ${acting.approved_by}` : ""}
          </div>
        </Box>
      )}

      {upcoming && (
        <Box tone="violet" icon="🟣">
          <b>You will be Acting HOD of {upcoming.department}</b> from {fmtD(upcoming.start_date)} to {fmtD(upcoming.end_date)}.
          <div style={SUB}>
            Reason: {upcoming.reason}
            {upcoming.approved_by ? ` · Approved by ${upcoming.approved_by}` : ""}
          </div>
        </Box>
      )}

      {cov && (
        <Box tone="violet" icon="🟣">
          <b>{cov.teacher} is Acting HOD of {cov.department} until {fmtD(cov.end_date)}.</b>{" "}
          Your HOD powers return on {fmtD(cov.returns_on)}.
          <div style={SUB}>Reason: {cov.reason}</div>
        </Box>
      )}

      {pend.map((p) => (
        <Box key={p.id} tone="amber" icon="⏳">
          <b>Your nomination of {p.teacher}</b> as Acting HOD of {p.department} ({fmtD(p.start_date)} to {fmtD(p.end_date)}) <b>is waiting for admin approval.</b> You stay HOD until it is approved.
        </Box>
      ))}
    </div>
  );
}