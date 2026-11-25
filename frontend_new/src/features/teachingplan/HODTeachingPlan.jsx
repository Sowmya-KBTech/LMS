// Frontend/src/features/teachingplan/HODTeachingPlans.jsx
import React, { useEffect, useState } from "react";
import API from "../../api";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import "../../styles/TeachingPlans.css";
import DeliveryView from "./DeliveryView";   // COURSE PLAN (Part B)

const ORDER = { pending: 0, behind: 1, rejected: 2, ontrack: 3, approved: 4 };

const PREVIEW_COUNT = 5;

// status -> tint class (used for avatars, pills, badges)
const TINT_CLASS = {
  pending: "tp-tint--blue",
  approved: "tp-tint--green",
  ontrack: "tp-tint--green",
  behind: "tp-tint--amber",
  rejected: "tp-tint--red",
};
const tintClass = (status) => TINT_CLASS[status] || "tp-tint--green";

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const monLabel = (iso) => {
  const [, m, d] = (iso || "").split("-").map(Number);
  return m ? `${MON[m - 1]} ${d}` : iso;
};

// ================= SMALL PRESENTATIONAL HELPERS =================
function Pill({ tint, children }) {
  return <span className={`tp-pill ${tint}`}>{children}</span>;
}

function Avatar({ tint, large, children }) {
  return <div className={`tp-avatar${large ? " tp-avatar--lg" : ""} ${tint}`}>{children}</div>;
}

function Kpi({ label, value, variant }) {
  return (
    <div className="tp-kpi">
      <div className="tp-kpi-label">{label}</div>
      <div className={`tp-kpi-value${variant ? ` tp-kpi-value--${variant}` : ""}`}>{value}</div>
    </div>
  );
}

function Legend({ dot, children }) {
  return (
    <span className="tp-legend">
      <i className={`tp-legend-dot tp-legend-dot--${dot}`} />
      {children}
    </span>
  );
}

function Toast({ text }) {
  if (!text) return null;
  return <div className="tp-toast">{text}</div>;
}

// row-level helpers (composed from the primitives above)
function middle(p, openReview) {
  if (p.status === "pending")
    return <button className="tp-btn-primary" onClick={() => openReview(p)}>Review</button>;
  return <button className="tp-btn-outline" onClick={() => openReview(p)}>View</button>;
}

function statusPill(p) {
  const label = {
    pending: "Pending review",
    approved: "Approved",
    rejected: "Sent back",
    behind: "Behind schedule",
    ontrack: "On track",
  }[p.status] || "On track";
  return <Pill tint={tintClass(p.status)}>{label}</Pill>;
}

// ================= MAIN COMPONENT =================
export default function HODTeachingPlans() {
  const [open, setOpen] = useState(false);
  const [plans, setPlans] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [view, setView] = useState("list");
  const [sel, setSel] = useState(null);
  const [comment, setComment] = useState("");
  const [deciding, setDeciding] = useState(false);   // FIX #32: one click only
  const [toast, setToast] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [dept, setDept] = useState("");

  useEffect(() => {
    API.get("teaching-plans/department/")
      .then((res) => {
        if (Array.isArray(res.data)) {
          setPlans(res.data);
          const d = res.data.find((p) => p.department || p.dept_name);
          if (d) setDept(d.department || d.dept_name);
        }
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  const flash = (m) => { setToast(m); setTimeout(() => setToast(""), 2600); };

  const counts = plans.reduce((a, p) => { a[p.status] = (a[p.status] || 0) + 1; return a; }, {});
  const sorted = [...plans].sort((a, b) => ORDER[a.status] - ORDER[b.status]);

  const openReview = (p) => { setSel(p); setComment(""); setShowAll(false); setView("review"); window.scrollTo(0, 0); };
  const backToList = () => setView("list");

  const decide = async (action) => {
    if (deciding) return;                       // FIX #32: ignore a second click
    const cmt = comment.trim();
    if (action === "reject" && !cmt) { flash("Add a comment so the teacher knows what to fix"); return; }
    const newStatus = action === "approve" ? "approved" : "rejected";
    setDeciding(true);
    try {
      await API.post(`teaching-plans/${sel.id}/${action}/`, { comment: cmt });
    } catch (err) {
      // FIX #32: this used to be swallowed ("demo mode"), so a refused decision
      // still looked successful on screen. Show the real reason instead.
      flash(err?.response?.data?.detail || "Could not save the decision. Please try again.");
      setDeciding(false);
      return;
    }
    setDeciding(false);
    // NOTE: the decided footer below reads sel.hod_comment — keep the field name
    // the same here or the comment silently fails to render on re-open.
    setPlans((prev) => prev.map((p) => (p.id === sel.id ? { ...p, status: newStatus, hod_comment: cmt } : p)));
    flash(action === "approve" ? `Plan approved — published to ${sel.cls}` : `Plan sent back to ${sel.teacher} for revision`);
    backToList();
  };

  // ================= REVIEW VIEW =================
  if (view === "review" && sel) {
    const units = sel.units || [];
    const total = units.reduce((a, u) => a + (Number(u.hours) || 0), 0);
    const hoursMod = total > sel.allotted ? "over" : total < sel.allotted ? "under" : "match";
    const initials = sel.initials || "?";
    const shown = showAll ? units : units.slice(0, PREVIEW_COUNT);
    const hidden = units.length - shown.length;

    const badgeLabel = {
      pending: "Pending review",
      approved: "Approved",
      ontrack: "Approved",
      behind: "Behind schedule",
      rejected: "Sent back",
    }[sel.status] || "Pending review";

    return (
      <div className="app">
        <Navbar setOpen={setOpen} />
        <div className="layout">
          <Sidebar open={open} setOpen={setOpen} />
          <div className="main">
            <div className="content tp-pad-bottom">
              <div className="tp-card tp-w860">

                <div className="tp-review-back-wrap">
                  <button className="tp-back-btn" onClick={backToList}>← Back to plans</button>
                </div>

                <div className="tp-review-head">
                  <div className={`tp-avatar tp-avatar--lg ${tintClass("pending")}`}>{initials}</div>
                  <div className="tp-review-head-info">
                    <div className="tp-review-subject">{sel.subject}{sel.code ? ` – ${sel.code}` : ""}</div>
                    <div className="tp-review-meta">{sel.teacher} · {sel.cls} · {sel.sem}</div>
                  </div>
                  <span className={`tp-badge ${tintClass(sel.status)}`}>{badgeLabel}</span>
                </div>

                <div className="tp-stats">
                  <div className={`tp-stat${hoursMod === "match" ? " tp-stat--match" : ""}`}>
                    <div className={`tp-stat-label tp-hours--${hoursMod}`}>Hours</div>
                    <div className={`tp-stat-value tp-hours--${hoursMod}`}>
                      {total} / {sel.allotted} <span className="tp-stat-sub">planned</span>
                    </div>
                  </div>
                  <div className="tp-stat">
                    <div className="tp-stat-label">Class days</div>
                    <div className="tp-stat-value">{units.length} classes</div>
                  </div>
                </div>

                <div className="tp-units">
                  <div className="tp-units-head">
                    <div className="tp-units-title">Topic for each class</div>
                    <div className="tp-units-count">showing {shown.length} of {units.length}</div>
                  </div>

                  <div className={`tp-units-list${showAll ? " tp-units-list--scroll" : ""}`}>
                    {shown.map((u, i) => (
                      <div className="tp-unit" key={i}>
                        <div className="tp-unit-idx">{i + 1}</div>
                        <div className="tp-unit-topic">
                          {u.topic}
                          {/* COURSE PLAN: unit, teaching mode and method so the HOD can review how it is taught */}
                          {(u.unit_no || u.mode_label) && (
                            <div className="tp-unit-sub">
                              {[u.unit_no ? `Unit ${u.unit_no}` : "", u.mode_label, u.method_label,
                                u.class_activity_label, u.beyond_activity_label,
                                (u.outcome_codes || []).join(", ")].filter(Boolean).join(" · ")}
                            </div>
                          )}
                        </div>
                        <div className="tp-unit-meta">
                          {u.hours} hr{Number(u.hours) === 1 ? "" : "s"}{u.due ? ` · ${monLabel(u.due)}` : ""}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* toggle sits OUTSIDE the scroll box — otherwise it scrolls
                      out of sight the moment the list is expanded */}
                  {units.length > PREVIEW_COUNT && (
                    <div className="tp-units-toggle" onClick={() => setShowAll((v) => !v)}>
                      {showAll ? "Show fewer" : `Show all ${units.length} classes (${hidden} more)`}
                    </div>
                  )}
                </div>

                {/* COURSE PLAN (Part B): what was actually delivered, read-only for the HOD */}
                {["approved", "ontrack", "behind"].includes(sel.status) && (
                  <div className="tp-units">
                    <div className="tp-units-head"><div className="tp-units-title">Planned vs delivered</div></div>
                    <DeliveryView planId={sel.id} readOnly />
                  </div>
                )}

                {sel.status === "pending" ? (
                  <>
                    <div className="tp-comment-sec">
                      <div className="tp-comment-label">Comments for teacher (needed if sending back)</div>
                      <textarea
                        className="tp-textarea"
                        value={comment}
                        onChange={(e) => setComment(e.target.value)}
                        placeholder="Add feedback here…"
                      />
                    </div>

                    <div className="tp-actions">
                      <span className="tp-actions-hint">Approving publishes the plan to the class.</span>
                      <button className="tp-btn-sendback" disabled={deciding} onClick={() => decide("reject")}>Send back</button>
                                           <button className="tp-btn-approve" disabled={deciding} onClick={() => decide("approve")}>
                                            {deciding ? "Saving…" : "Approve"}
                                           </button>
                    </div>
                  </>
                ) : (
                  <div className="tp-decided">
                    <div className={`tp-decided-title tp-decided-title--${sel.status === "rejected" ? "rejected" : "approved"}`}>
                      {sel.status === "rejected" ? "Sent back for revision" : "Approved · published to the class"}
                    </div>
                    {sel.hod_comment ? (
                      <div className="tp-decided-comment">Your comment: {sel.hod_comment}</div>
                    ) : null}
                  </div>
                )}

              </div>
            </div>
          </div>
        </div>
        <Toast text={toast} />
      </div>
    );
  }

  // ================= LIST VIEW =================
  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            <h1 className="tp-title">Teaching plans</h1>
            <p className="tp-subtitle">
              {dept ? `${dept} department` : "Your department"} · plans submitted by your faculty
            </p>

            <div className="tp-kpi-grid">
              <Kpi label="Total plans" value={plans.length} />
              <Kpi label="Pending review" value={counts.pending || 0} variant="blue" />
              <Kpi label="On track" value={(counts.ontrack || 0) + (counts.approved || 0)} variant="green" />
              <Kpi label="Behind / sent back" value={(counts.behind || 0) + (counts.rejected || 0)} variant="amber" />
            </div>

            <div className="tp-list">
              {sorted.length === 0 ? (
                <div className="tp-empty">
                  {loaded ? "No teaching plans submitted in your department yet." : "Loading…"}
                </div>
              ) : sorted.map((p) => (
                <div className="tp-row" key={p.id}>
                  <Avatar tint={tintClass(p.status)}>{p.initials}</Avatar>
                  <div className="tp-row-main">
                    <div className="tp-row-subject">{p.subject}{p.code ? ` - ${p.code}` : ""}</div>
                    <div className="tp-row-meta">{p.teacher} · {p.cls}</div>
                  </div>
                  {middle(p, openReview)}
                  {statusPill(p)}
                </div>
              ))}
            </div>

            <div className="tp-legend-row">
              <Legend dot="blue">Awaiting your approval</Legend>
              <Legend dot="green">Approved and on schedule</Legend>
              <Legend dot="amber">Planned date passed, unit not done</Legend>
              <Legend dot="red">Sent back for revision</Legend>
            </div>

          </div>
        </div>
      </div>
      <Toast text={toast} />
    </div>
  );
}