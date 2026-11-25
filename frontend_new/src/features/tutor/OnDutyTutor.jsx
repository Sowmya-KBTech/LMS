import { useEffect, useState } from "react";
import API from "../../api";
import "../../styles/Attendance.css";

const fmtDate = (iso) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}-${m}-${y}`;
};

export default function OnDutyTutor() {
  const [list, setList]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [remarks, setRemarks] = useState({});   // { [id]: "text" }
  const [busyId, setBusyId]   = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await API.get("users/tutor/od/");
      setList(res.data?.results || res.data || []);
    } catch (err) {
      console.error("Tutor OD load error:", err);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const act = async (id, action) => {
    setBusyId(id);
    try {
      await API.post(`users/tutor/od/${id}/action/`, {
        action,
        remark: remarks[id] || "",
      });
      // remove the handled request from the queue
      setList((prev) => prev.filter((r) => r.id !== id));
      setRemarks((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    } catch (err) {
      alert(err?.response?.data?.detail || "Could not submit action.");
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
      <h2 className="att-card-title">Student On-Duty Requests · Pending your approval</h2>

      {list.length === 0 ? (
        <div className="att-state"><p>No student on-duty requests waiting for your approval.</p></div>
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
                    {r.category_label} · {fmtDate(r.from_date)} → {fmtDate(r.to_date)}
                  </div>
                </div>

                {r.reason && <div className="att-od-reason-cell">{r.reason}</div>}

                <input
                  className="att-od-remark-inline"
                  type="text"
                  placeholder="Remark (optional)"
                  value={remarks[r.id] || ""}
                  onChange={(e) => setRemarks((prev) => ({ ...prev, [r.id]: e.target.value }))}
                />

                <div className="att-od-actions">
                  <button
                    className="att-od-approve"
                    onClick={() => act(r.id, "approve")}
                    disabled={busyId === r.id}
                  >
                    {busyId === r.id ? "Working…" : "Approve"}
                  </button>
                  <button
                    className="att-od-reject"
                    onClick={() => act(r.id, "reject")}
                    disabled={busyId === r.id}
                  >
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