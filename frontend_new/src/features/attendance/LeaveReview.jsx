// WAVE 1 - student leave requests waiting for the class in-charge or the HOD.
//   <LeaveReview who="tutor" />  in My Class → Student Leave
//   <LeaveReview who="hod" />    in My Department → Student leave
import { useEffect, useState } from "react";
import API from "../../api";
import "../../styles/Attendance.css";

const fmtDate = (iso) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}-${m}-${y}`;
};

export default function LeaveReview({ who = "tutor" }) {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [remarks, setRemarks] = useState({});   // { [id]: "text" }
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");

  const base = who === "hod" ? "users/hod/leave/" : "users/tutor/leave/";

  useEffect(() => {
    setLoading(true);
    API.get(base)
      .then((res) => setList(res.data?.results || res.data || []))
      .catch(() => setError("Couldn't load the leave requests. Refresh the page to try again."))
      .finally(() => setLoading(false));
  }, [base]);

  const act = async (id, action) => {
    setError("");
    if (action === "reject" && !(remarks[id] || "").trim()) {
      setError("Write a remark before rejecting - the student sees it.");
      return;
    }
    setBusyId(id);
    try {
      await API.post(`${base}${id}/action/`, { action, remark: remarks[id] || "" });
      setList((prev) => prev.filter((r) => r.id !== id));
      setRemarks((prev) => { const next = { ...prev }; delete next[id]; return next; });
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not submit the decision.");
    } finally {
      setBusyId(null);
    }
  };

  if (loading) {
    return (
      <div className="att-card">
        <div className="att-state"><div className="att-spinner" /><p>Loading…</p></div>
      </div>
    );
  }

  return (
    <div className="att-card">
      <h2 className="att-card-title">
        Student Leave Requests · {who === "hod" ? "Final approval" : "Pending your approval"}
      </h2>
      {error && <p className="att-od-meta" style={{ color: "#B42318", marginBottom: 10 }}>{error}</p>}

      {list.length === 0 ? (
        <div className="att-state"><p>No student leave requests waiting for your approval.</p></div>
      ) : (
        <div className="att-od-list">
          {list.map((r) => (
            <div key={r.id} className="att-od-item">
              <div className="att-od-row">
                <div className="att-od-main">
                  <div className="att-od-cat">
                    {r.student_name}
                    {r.student_roll_no && <span className="att-od-roll">{r.student_roll_no}</span>}
                  </div>
                  <div className="att-od-meta">
                    {r.leave_type_label} · {fmtDate(r.from_date)} → {fmtDate(r.to_date)} · {r.days} day{r.days === 1 ? "" : "s"}
                  </div>
                  {who === "hod" && r.tutor_reviewed_by_name && (
                    <div className="att-od-meta">Approved by class in-charge {r.tutor_reviewed_by_name}
                      {r.tutor_remark ? ` · "${r.tutor_remark}"` : ""}</div>
                  )}
                </div>

                {r.reason && <div className="att-od-reason-cell">{r.reason}</div>}

                <input
                  className="att-od-remark-inline"
                  type="text"
                  placeholder="Remark (needed to reject)"
                  value={remarks[r.id] || ""}
                  onChange={(e) => setRemarks((prev) => ({ ...prev, [r.id]: e.target.value }))}
                />

                <div className="att-od-actions">
                  <button className="att-od-approve" onClick={() => act(r.id, "approve")} disabled={busyId === r.id}>
                    {busyId === r.id ? "Working…" : "Approve"}
                  </button>
                  <button className="att-od-reject" onClick={() => act(r.id, "reject")} disabled={busyId === r.id}>
                    Reject
                  </button>
                </div>
              </div>

              {r.proof && (
                <a href={r.proof} target="_blank" rel="noreferrer" className="att-od-proof">View proof</a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
