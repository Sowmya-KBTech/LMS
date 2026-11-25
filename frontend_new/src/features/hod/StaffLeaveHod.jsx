import { useEffect, useState } from "react";
import API from "../../api";
import "../../styles/Attendance.css";
import "../../styles/StaffLeave.css";

const STATUS_HELP = [
  { key: "pending", text: "Waiting for HOD", help: "Waiting for HOD approval" },
  { key: "approved", text: "Approved", help: "HOD approved the leave" },
  { key: "rejected", text: "Rejected", help: "HOD rejected the leave" },
  { key: "cancelled", text: "Cancelled", help: "Teacher cancelled the request" },
];

const SUB_NOTE =
  "These classes may need a substitute teacher. Approving leave does not assign one.";

const fmtDate = (iso) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}-${m}-${y}`;
};

const badgeOf = (status) =>
  STATUS_HELP.find((s) => s.key === status) || { key: status, text: status };

const initials = (name = "") =>
  name.replace(/[^A-Za-z ]/g, " ").trim().split(/\s+/).slice(0, 2)
    .map((w) => w[0]).join("").toUpperCase() || "?";

const errText = (err) => {
  const data = err?.response?.data;
  if (!data) return "Something went wrong. Try again.";
  if (typeof data === "string") return data;
  return data.detail || "Could not submit action.";
};

export default function StaffLeaveHod() {
  const [tab, setTab] = useState("pending");
  const [pending, setPending] = useState([]);
  const [history, setHistory] = useState([]);
  const [today, setToday] = useState([]);
  const [loading, setLoading] = useState(true);

  const [remarks, setRemarks] = useState({});
  const [busyId, setBusyId] = useState(null);
  const [rowError, setRowError] = useState({});
  const [expanded, setExpanded] = useState({});   // { [id]: periods[] }

  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [p, h, t] = await Promise.all([
        API.get("users/hod/staff-leave/"),
        API.get("users/hod/staff-leave/history/"),
        API.get("users/hod/staff-leave/on-leave-today/"),
      ]);
      setPending(p.data?.results || p.data || []);
      setHistory(h.data?.results || h.data || []);
      setToday(t.data?.results || t.data || []);
    } catch (err) {
      console.error("HOD staff leave load error:", err);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const act = async (id, action) => {
    const remark = (remarks[id] || "").trim();
    if (action === "reject" && !remark) {
      setRowError((prev) => ({ ...prev, [id]: "Add a remark so the teacher knows why." }));
      return;
    }
    setBusyId(id);
    setRowError((prev) => ({ ...prev, [id]: "" }));
    try {
      await API.post(`users/hod/staff-leave/${id}/action/`, { action, remark });
      setRemarks((prev) => { const next = { ...prev }; delete next[id]; return next; });
      await load();
    } catch (err) {
      setRowError((prev) => ({ ...prev, [id]: errText(err) }));
    } finally {
      setBusyId(null);
    }
  };

  // affected periods come from the detail endpoint, loaded only when expanded
  const toggleClasses = async (id) => {
    if (expanded[id]) {
      setExpanded((prev) => { const next = { ...prev }; delete next[id]; return next; });
      return;
    }
    try {
      const res = await API.get(`users/staff-leave/${id}/`);
      setExpanded((prev) => ({ ...prev, [id]: res.data.affected_periods || [] }));
    } catch (err) {
      alert(errText(err));
    }
  };

  const openDetail = async (id) => {
    setDetailLoading(true);
    setDetail({ id });
    try {
      const res = await API.get(`users/staff-leave/${id}/`);
      setDetail(res.data);
    } catch (err) {
      alert(errText(err));
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const periodsBox = (periods, note) => (
    <div className="sl-classes">
      <div className="sl-classes-title">Classes during this leave ({periods.length})</div>
      {periods.length === 0 ? (
        <div className="sl-classes-empty">No classes in these dates.</div>
      ) : (
        <ul className="sl-classes-list">
          {periods.map((p) => (
            <li key={p.entry_id + p.date}>
              <span className="sl-classes-day">{p.day_of_week.slice(0, 3)} {fmtDate(p.date)}</span>
              <span>Period {p.period_no}: {p.subject}, {p.course} Year {p.year}</span>
            </li>
          ))}
        </ul>
      )}
      {note && <div className="sl-classes-note">{note}</div>}
    </div>
  );

  const dateRange = (r) =>
    `${fmtDate(r.from_date)}${r.to_date !== r.from_date ? ` → ${fmtDate(r.to_date)}` : ""}, ` +
    `${r.session !== "full" ? r.session_label : `${Number(r.days)} ${Number(r.days) === 1 ? "day" : "days"}`}`;

  if (loading) {
    return (
      <div className="att-card">
        <div className="att-state"><div className="att-spinner" /><p>Loading…</p></div>
      </div>
    );
  }

  // ── details view replaces the list ──
  if (detail) {
    return (
      <div className="att-card">
        <div className="sl-detail-head">
          <button className="att-btn-outline" onClick={() => setDetail(null)}>← Back</button>
          <h2 className="att-card-title sl-detail-title">Leave details</h2>
          {detail.status && (
            <span className={`att-od-badge ${badgeOf(detail.status).key}`}>
              {badgeOf(detail.status).text}
            </span>
          )}
        </div>
        {detailLoading ? (
          <div className="att-state"><div className="att-spinner" /><p>Loading…</p></div>
        ) : (
          <div className="sl-detail">
            <div className="sl-row"><div className="sl-k">Teacher</div>
              <div>{detail.teacher_name}{detail.teacher_designation ? `, ${detail.teacher_designation}` : ""}{detail.department_name ? `, ${detail.department_name}` : ""}</div>
            </div>
            <div className="sl-row"><div className="sl-k">Leave type</div><div>{detail.leave_type_label}</div></div>
            <div className="sl-row"><div className="sl-k">From and to</div><div>{dateRange(detail)}</div></div>
            <div className="sl-row"><div className="sl-k">Number of days</div><div>{Number(detail.days)}</div></div>
            <div className="sl-row"><div className="sl-k">Reason</div><div>{detail.reason}</div></div>
            <div className="sl-row"><div className="sl-k">Proof</div>
              <div>{detail.proof_url
                ? <a className="att-od-proof" href={detail.proof_url} target="_blank" rel="noreferrer">View proof</a>
                : <span className="sl-na">Not attached</span>}</div>
            </div>
            <div className="sl-row"><div className="sl-k">Applied on</div><div>{fmtDate((detail.created_at || "").slice(0, 10))}</div></div>
            <div className="sl-row"><div className="sl-k">Decision</div>
              <div>{detail.decided_at
                ? `${badgeOf(detail.status).text} on ${fmtDate(detail.decided_at.slice(0, 10))}`
                  + (detail.decided_by_name ? ` by ${detail.decided_by_name}` : "")
                  + (detail.decided_as_acting ? " (Acting HOD)" : "")
                : <span className="sl-na">Not decided yet</span>}</div>
            </div>
            <div className="sl-row"><div className="sl-k">HOD remark</div>
              <div>{detail.hod_remark || <span className="sl-na">None</span>}</div>
            </div>
            <div className="sl-row"><div className="sl-k">Affected periods</div>
              <div>{periodsBox(detail.affected_periods || [], SUB_NOTE)}</div>
            </div>
            <div className="sl-row"><div className="sl-k">Substitute status</div>
              <div><span className="sl-na">Not arranged. Substitution is a later phase.</span></div>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="sl-hod-wrap">
      <div className="att-card">
        <div className="att-tabs sl-inner-tabs">
          <button className={`att-tab${tab === "pending" ? " active" : ""}`} onClick={() => setTab("pending")}>
            Pending ({pending.length})
          </button>
          <button className={`att-tab${tab === "history" ? " active" : ""}`} onClick={() => setTab("history")}>
            History
          </button>
        </div>

        {/* ════════ PENDING ════════ */}
        {tab === "pending" && (
          pending.length === 0 ? (
            <div className="att-state"><p>No leave requests waiting for you.</p></div>
          ) : (
            <div className="att-od-list">
              {pending.map((r) => (
                <div key={r.id} className="att-od-item">
                  <div className="att-od-row">
                    <div className="sl-fac">
                      <div className="sl-avatar">{initials(r.teacher_name)}</div>
                      <div>
                        <b>{r.teacher_name}</b>
                        <span>{r.teacher_designation}</span>
                      </div>
                    </div>
                    <div className="att-od-main">
                      <div className="att-od-cat">{r.leave_type_label}</div>
                      <div className="att-od-dates">{dateRange(r)}</div>
                    </div>
                    <div className="att-od-actions">
                      <span className="att-od-roll">Applied {fmtDate((r.created_at || "").slice(0, 10))}</span>
                      <button className="att-btn-outline" onClick={() => openDetail(r.id)}>Details</button>
                    </div>
                  </div>

                  <div className="sl-reason">{r.reason}</div>

                  {r.covering_warning && (
                    <div className="sl-warn sl-indent">⚠ {r.covering_warning}</div>
                  )}

                  {r.proof_url && (
                    <a className="att-od-proof sl-indent" href={r.proof_url} target="_blank" rel="noreferrer">
                      View proof
                    </a>
                  )}

                  <button className="sl-link sl-indent" onClick={() => toggleClasses(r.id)}>
                    {expanded[r.id] ? "Hide classes affected" : "Show classes affected"}
                  </button>
                  {expanded[r.id] && periodsBox(expanded[r.id], SUB_NOTE)}

                  <div className="sl-review">
                    <div>
                      <input
                        className="att-od-remark-input"
                        type="text"
                        placeholder="Remark (needed if you reject)"
                        aria-label={`Remark for ${r.teacher_name}`}
                        value={remarks[r.id] || ""}
                        onChange={(e) => setRemarks((prev) => ({ ...prev, [r.id]: e.target.value }))}
                      />
                      {rowError[r.id] && <div className="sl-error">{rowError[r.id]}</div>}
                    </div>
                    <div className="att-od-action-row">
                      <button className="att-od-approve" onClick={() => act(r.id, "approve")} disabled={busyId === r.id}>
                        {busyId === r.id ? "Working…" : "Approve"}
                      </button>
                      <button className="att-od-reject" onClick={() => act(r.id, "reject")} disabled={busyId === r.id}>
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )
        )}

        {/* ════════ HISTORY ════════ */}
        {tab === "history" && (
          history.length === 0 ? (
            <div className="att-state"><p>No decided requests yet.</p></div>
          ) : (
            <table className="sl-table">
              <thead>
                <tr>
                  <th>Faculty</th><th>Type</th><th>Dates</th><th>Days</th>
                  <th>Decision</th><th>Remark</th><th></th>
                </tr>
              </thead>
              <tbody>
                {history.map((r) => (
                  <tr key={r.id}>
                    <td>{r.teacher_name}</td>
                    <td>{r.leave_type_label}</td>
                    <td>{fmtDate(r.from_date)}{r.to_date !== r.from_date ? ` → ${fmtDate(r.to_date)}` : ""}</td>
                    <td>{Number(r.days)}</td>
                    <td><span className={`att-od-badge ${badgeOf(r.status).key}`}>{badgeOf(r.status).text}</span></td>
                    <td className="sl-muted">{r.hod_remark || "—"}</td>
                    <td><button className="att-btn-outline" onClick={() => openDetail(r.id)}>Details</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}

        <div className="sl-legend">
          <div className="sl-legend-title">What each status means</div>
          {STATUS_HELP.map((s) => (
            <div key={s.key} className="sl-legend-row">
              <span className={`att-od-badge ${s.key}`}>{s.text}</span>
              <span>{s.help}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ════════ ON LEAVE TODAY ════════ */}
      <div className="att-card">
        <h2 className="att-card-title">On leave today</h2>
        {today.length === 0 ? (
          <div className="att-state"><p>Everyone is in today.</p></div>
        ) : (
          <div className="sl-today">
            {today.map((r) => (
              <div key={r.id} className="sl-fac">
                <div className="sl-avatar">{initials(r.teacher_name)}</div>
                <div>
                  <b>{r.teacher_name}</b>
                  <span>{r.leave_type_label}, until {fmtDate(r.to_date)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}