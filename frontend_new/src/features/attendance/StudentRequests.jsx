// Student requests - on duty and leave in one list, for the people who review them.
//   <StudentRequests who="tutor" />  in My Class → Student requests
//   <StudentRequests who="hod" />    in My Department → Student requests
// Replaces the separate "Student on duty" and "Student leave" pages. The two kinds
// stay separate underneath: approved on duty counts as present, approved leave
// shows "On leave" and does not. Every row says which kind it is.
import { useEffect, useMemo, useState } from "react";
import API from "../../api";
import "../../styles/Attendance.css";

const fmtDate = (iso) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}-${m}-${y}`;
};

const KINDS = [["all", "All"], ["od", "On duty"], ["leave", "Leave"]];
const SHOW = [["waiting", "Waiting for me"], ["decided", "Already decided"]];

// what happened to a request this reviewer already decided
function outcome(r, who) {
  if (r.status === "approved") return ["approved", "Approved"];
  if (r.status === "rejected") return ["rejected", "Rejected"];
  if (r.status === "cancelled") return ["cancelled", "Cancelled by student"];
  if (who === "tutor" && r.stage === "awaiting_hod") return ["awaiting_hod", "Sent to HOD"];
  return ["awaiting_hod", r.stage_label || "In progress"];
}

export default function StudentRequests({ who = "hod" }) {
  const [kind, setKind] = useState("all");
  const [show, setShow] = useState("waiting");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [remarks, setRemarks] = useState({});   // { "od-12": "text" }
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    let live = true;
    const q = show === "decided" ? "?show=decided" : "";
    setLoading(true);
    setError("");
    Promise.all([
      API.get(`users/${who}/od/${q}`).catch(() => null),
      API.get(`users/${who}/leave/${q}`).catch(() => null),
    ]).then(([od, lv]) => {
      if (!live) return;
      if (!od && !lv) setError("Couldn't load the requests. Refresh the page to try again.");
      const list = (res) => res?.data?.results || res?.data || [];
      const at = (r) => (show === "decided" ? r[`${who}_reviewed_at`] : r.created_at) || "";
      const merged = [
        ...list(od).map((r) => ({ ...r, kind: "od", key: `od-${r.id}` })),
        ...list(lv).map((r) => ({ ...r, kind: "leave", key: `leave-${r.id}` })),
      ].sort((a, b) => (show === "decided" ? at(b).localeCompare(at(a)) : at(a).localeCompare(at(b))));
      setRows(merged);
    }).finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [who, show]);

  const visible = useMemo(() => rows.filter((r) => kind === "all" || r.kind === kind), [rows, kind]);
  const count = (k) => rows.filter((r) => k === "all" || r.kind === k).length;

  const act = async (r, action) => {
    setError("");
    const remark = (remarks[r.key] || "").trim();
    if (action === "reject" && r.kind === "leave" && !remark) {
      setError("Write a remark before rejecting leave - the student sees it.");
      return;
    }
    setBusy(r.key);
    try {
      await API.post(`users/${who}/${r.kind}/${r.id}/action/`, { action, remark });
      setRows((prev) => prev.filter((x) => x.key !== r.key));
      setRemarks((prev) => { const next = { ...prev }; delete next[r.key]; return next; });
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not submit the decision.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="att-card">
      <h2 className="att-card-title">
        Student requests · {who === "hod" ? "Final approval" : "Class in-charge approval"}
      </h2>

      <div className="att-req-bar">
        <div className="ems-seg crg-tabs" role="tablist" aria-label="Type">
          {KINDS.map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={kind === k} className={kind === k ? "on" : ""}
              onClick={() => setKind(k)}>
              {l}{!loading && ` (${count(k)})`}
            </button>
          ))}
        </div>
        <div className="ems-seg crg-tabs" role="tablist" aria-label="Show">
          {SHOW.map(([k, l]) => (
            <button key={k} type="button" role="tab" aria-selected={show === k} className={show === k ? "on" : ""}
              onClick={() => setShow(k)}>{l}</button>
          ))}
        </div>
      </div>

      {error && <p className="att-od-meta" style={{ color: "#B42318", marginBottom: 10 }}>{error}</p>}

      {loading ? (
        <div className="att-state"><div className="att-spinner" /><p>Loading…</p></div>
      ) : visible.length === 0 ? (
        <div className="att-state">
          <p>{show === "waiting" ? "No requests waiting for your approval." : "No decided requests yet."}</p>
        </div>
      ) : (
        <div className="att-od-list">
          {visible.map((r) => {
            const [cls, label] = outcome(r, who);
            return (
              <div key={r.key} className="att-od-item">
                <div className="att-od-row">
                  <div className="att-od-main">
                    <div className="att-od-cat">
                      {r.student_name}
                      {r.student_roll_no && <span className="att-od-roll">{r.student_roll_no}</span>}
                    </div>
                    <div className="att-od-meta">
                      {r.kind === "od"
                        ? <span className="att-req-kind od">On duty · counts as present</span>
                        : <span className="att-req-kind leave">Leave</span>}
                      {" "}{r.kind === "od" ? r.category_label : r.leave_type_label}
                      {" · "}{fmtDate(r.from_date)} → {fmtDate(r.to_date)}
                      {r.kind === "leave" && r.days ? ` · ${r.days} day${r.days === 1 ? "" : "s"}` : ""}
                    </div>
                    {who === "hod" && r.tutor_reviewed_by_name && (
                      <div className="att-od-meta">Approved by class in-charge {r.tutor_reviewed_by_name}
                        {r.tutor_remark ? ` · "${r.tutor_remark}"` : ""}</div>
                    )}
                  </div>

                  {r.reason && <div className="att-od-reason-cell">{r.reason}</div>}

                  {show === "waiting" ? (
                    <>
                      <input
                        className="att-od-remark-inline"
                        type="text"
                        placeholder={r.kind === "leave" ? "Remark (needed to reject)" : "Remark (optional)"}
                        value={remarks[r.key] || ""}
                        onChange={(e) => setRemarks((prev) => ({ ...prev, [r.key]: e.target.value }))}
                      />
                      <div className="att-od-actions">
                        <button className="att-od-approve" onClick={() => act(r, "approve")} disabled={busy === r.key}>
                          {busy === r.key ? "Working…" : "Approve"}
                        </button>
                        <button className="att-od-reject" onClick={() => act(r, "reject")} disabled={busy === r.key}>
                          Reject
                        </button>
                      </div>
                    </>
                  ) : (
                    <div className="att-od-actions">
                      <span className={`att-od-badge ${cls}`}>{label}</span>
                    </div>
                  )}
                </div>

                {show === "decided" && r[`${who}_remark`] && (
                  <div className="att-od-remark">Your remark: {r[`${who}_remark`]}</div>
                )}
                {r.proof && (
                  <a href={r.proof} target="_blank" rel="noreferrer" className="att-od-proof">View proof</a>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
