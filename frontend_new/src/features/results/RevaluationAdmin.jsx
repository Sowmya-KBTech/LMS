import { useEffect, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../styles/Attendance.css";

export default function RevaluationAdmin({ embedded = false }) {
  const [open, setOpen] = useState(false);

  // window control
  const [semester, setSemester] = useState("");
  const [window_, setWindow] = useState(null);   // current window status
  const [feeAmount, setFeeAmount] = useState("");
  const [savingWindow, setSavingWindow] = useState(false);

  // review list
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [revisedInputs, setRevisedInputs] = useState({}); // { [reqId]: markValue }

  // ── load window status when semester changes ──
  const loadWindow = (sem) => {
    if (!sem) { setWindow(null); return; }
    API.get(`/revaluation-window/status/?semester=${sem}`)
      .then((res) => {
        setWindow(res.data);
        setFeeAmount(res.data?.fee_amount ?? "");
      });
  };

  // ── load all review requests ──
  const loadRequests = () => {
    setLoading(true);
    API.get("/revaluations/review/")
      .then((res) => setRequests(res.data?.results || res.data || []))
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadRequests(); }, []);
  useEffect(() => { loadWindow(semester); }, [semester]);

  // ── open / close window ──
  const setWindowState = async (isOpen) => {
    if (!semester) return alert("Select a semester first.");
    if (isOpen && (feeAmount === "" || Number(feeAmount) < 0))
      return alert("Enter a valid fee amount to open the portal.");

    setSavingWindow(true);
    try {
      const res = await API.post("/revaluation-window/", {
        semester: Number(semester),
        is_open: isOpen,
        fee_amount: feeAmount || 0,
      });
      setWindow(res.data);
      alert(isOpen ? "Revaluation portal opened." : "Revaluation portal closed.");
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to update window.");
    } finally {
      setSavingWindow(false);
    }
  };

  // ── process a request: revise or retain ──
  const processRequest = async (req, retain) => {
    const payload = retain
      ? { retain: true }
      : { revised_marks: revisedInputs[req.id] };

    if (!retain && (payload.revised_marks === undefined || payload.revised_marks === "")) {
      return alert("Enter the revised mark, or click Retain.");
    }

    try {
      await API.post(`/revaluations/${req.id}/process/`, payload);
      loadRequests();
    } catch (err) {
      alert(err.response?.data?.detail || "Failed to process request.");
    }
  };

  const statusLabel = (s) => ({
    pending_review: "Pending Review",
    revised: "Revised",
    retained: "Retained",
    pending_payment: "Awaiting Payment",
  }[s] || s);

  const body = (
    <>
      <div className="att-header">
        <div>
          <h1 className="att-title">Revaluation — Admin</h1>
          <p className="att-subtitle">Open the portal, set the fee, and review requests</p>
        </div>
      </div>

      {/* ===== WINDOW CONTROL ===== */}
      <div className="att-card">
        <h2 className="att-card-title">Revaluation Portal</h2>

        <div className="att-filter-grid">
          <div className="att-field">
            <label className="att-label">Semester</label>
            <select className="att-input" value={semester}
              onChange={(e) => setSemester(e.target.value)}>
              <option value="">— Select Semester —</option>
              {[1,2,3,4,5,6,7,8].map((s) => <option key={s} value={s}>Semester {s}</option>)}
            </select>
          </div>

          <div className="att-field">
            <label className="att-label">Revaluation Fee (₹)</label>
            <input className="att-input" type="number" min={0}
              value={feeAmount}
              onChange={(e) => setFeeAmount(e.target.value)}
              placeholder="e.g. 500"
              disabled={!semester} />
          </div>
        </div>

        {semester && (
          <div className="att-summary-row" style={{ alignItems: "center", marginTop: 8 }}>
            <span className={`att-chip ${window_?.is_open ? "present" : "absent"}`}>
              {window_?.is_open ? "Portal OPEN" : "Portal CLOSED"}
            </span>
            {window_?.is_open && window_?.fee_amount != null && (
              <span className="att-chip">Fee: ₹{window_.fee_amount}</span>
            )}

            <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
              {window_?.is_open ? (
                <button className="att-btn-outline" onClick={() => setWindowState(false)} disabled={savingWindow}>
                  {savingWindow ? "…" : "Close Portal"}
                </button>
              ) : (
                <button className="att-save-btn" onClick={() => setWindowState(true)}
                  disabled={savingWindow || window_?.can_open === false}
                  title={window_?.can_open === false ? "No student has this semester as their latest published examination" : undefined}>
                  {savingWindow ? "…" : "Open Portal"}
                </button>
              )}
            </span>
          </div>
        )}

        {/* MEETING POINT 4: revaluation only for the latest published examination */}
        {semester && window_ && window_.can_open !== undefined && !window_.is_open && (
          <p className="att-hint" style={{ marginTop: 8, fontSize: 14, color: window_.can_open ? "#2e7d32" : "#b23b3b" }}>
            {window_.can_open
              ? `Semester ${semester} is the latest published examination for ${window_.eligible_students} student${window_.eligible_students === 1 ? "" : "s"}.`
              : `Semester ${semester} can't be opened: its results aren't published yet, or a later semester has already been published.`}
          </p>
        )}
      </div>

      {/* ===== REVIEW LIST ===== */}
      <div className="att-card">
        <h2 className="att-card-title">Revaluation Requests</h2>

        {loading ? (
          <div className="att-state"><div className="att-spinner" /><p>Loading requests…</p></div>
        ) : requests.length === 0 ? (
          <div className="att-state"><p>No revaluation requests yet.</p></div>
        ) : (
          <div className="att-table-wrap">
            <table className="att-table">
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Roll No</th>
                  <th>Subject</th>
                  <th className="center">Sem</th>
                  <th className="center">Current</th>
                  <th className="center">Status</th>
                  <th className="center">Revised</th>
                  <th className="center">Action</th>
                </tr>
              </thead>
              <tbody>
                {requests.map((r) => {
                  const done = r.status === "revised" || r.status === "retained";
                  return (
                    <tr key={r.id}>
                      <td className="att-td-name">{r.student_name}</td>
                      <td><span className="att-roll">{r.student_roll_no || "—"}</span></td>
                      <td>{r.subject_code ? `${r.subject_code} — ` : ""}{r.subject_name}</td>
                      <td className="center">{r.semester}</td>
                      <td className="center"><b>{r.current_marks ?? "—"}</b></td>
                      <td className="center">
                        <span style={{
                          fontSize: 14,
                          color: r.status === "revised" ? "#16a34a"
                                : r.status === "retained" ? "#5D5A6B"
                                : "#8A4B0A"
                        }}>
                          {statusLabel(r.status)}
                        </span>
                      </td>
                      <td className="center">
                        {done ? (
                          r.revised_marks ?? "—"
                        ) : (
                          <input
                            className="att-input"
                            type="number"
                            style={{ width: 80 }}
                            value={revisedInputs[r.id] ?? ""}
                            onChange={(e) =>
                              setRevisedInputs((p) => ({ ...p, [r.id]: e.target.value }))
                            }
                          />
                        )}
                      </td>
                      <td className="center">
                        {done ? (
                          <span style={{ color: "#85839A", fontSize: 14 }}>Processed</span>
                        ) : (
                          <div style={{ display: "flex", gap: 6, justifyContent: "center" }}>
                            <button className="att-save-btn" style={{ padding: "4px 10px" }}
                              onClick={() => processRequest(r, false)}>
                              Revise
                            </button>
                            <button className="att-btn-outline" style={{ padding: "4px 10px" }}
                              onClick={() => processRequest(r, true)}>
                              Retain
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );

  if (embedded) return body;

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="att-page">{body}</div>
          </div>
        </div>
      </div>
    </div>
  );
}