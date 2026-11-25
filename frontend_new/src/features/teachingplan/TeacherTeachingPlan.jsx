// Frontend/src/features/teachingplan/TeacherTeachingPlan.jsx
import React, { useEffect, useState } from "react";
import API from "../../api";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import "../../styles/TeachingPlans.css";
import CoursePlanEditor from "./CoursePlanEditor";   // COURSE PLAN (Part A)

const DEMO_SUBJECTS = [{ id: "demo1", label: "English Essentials – I" }];
const DEMO_SEMS = ["Semester 1"];


// status -> { label, action, tint class, bar class }
const STATUS_META = {
  approved:    { label: "Approved",      action: "View",     tint: "tp-tint--teal",  bar: "tp-subj-bar--teal" },
  submitted:   { label: "Submitted",     action: "View",     tint: "tp-tint--blue",  bar: "tp-subj-bar--blue" },
  draft:       { label: "Draft",         action: "Continue", tint: "tp-tint--amber", bar: "tp-subj-bar--amber" },
  rejected:    { label: "Needs changes", action: "Continue", tint: "tp-tint--red",   bar: "tp-subj-bar--red" },
  not_started: { label: "Not started",   action: "Start",    tint: "tp-tint--grey",  bar: "tp-subj-bar--grey" },
};

// A plan in these states is locked — the teacher can look but not edit.
const LOCKED_STATUSES = ["submitted", "approved"];

// ================= HELPERS =================
function CountBox({ n, label, variant }) {
  return (
    <div className={`tp-count tp-count--${variant}`}>
      <div className="tp-count-n">{n}</div>
      <div className="tp-count-label">{label}</div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <label className="tp-field-label">{label}</label>
      {children}
    </div>
  );
}

function TTLegend({ swatch, label }) {
  return (
    <span className="tp-tt-legend-item">
      <span className={`tp-tt-swatch tp-tt-swatch--${swatch}`} />
      {label}
    </span>
  );
}

function TimetablePanel({ subjectLabel, subjectId, onClose }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    API.get("teaching-plans/my_timetable/")
      .then((res) => setData(res.data))
      .catch(() => setData({ weekdays: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], rows: [] }));
  }, []);

  const isPlan = (c) => c && subjectId != null && String(c.subject_id) === String(subjectId);

  const cellClass = (c) => {
    if (!c) return "tp-tt-cell tp-tt-cell--free";
    if (isPlan(c)) return "tp-tt-cell tp-tt-cell--plan";
    return "tp-tt-cell tp-tt-cell--other";
  };

  return (
    <div className="tp-modal-overlay" onClick={onClose}>
      <div className="tp-modal" onClick={(e) => e.stopPropagation()}>
        <div className="tp-modal-head">
          <div>
            <div className="tp-modal-title">My assigned timetable</div>
            <div className="tp-modal-sub">by period</div>
          </div>
          <button className="tp-modal-close" aria-label="Close" onClick={onClose}>✕</button>
        </div>

        <div className="tp-modal-body">
          {!data ? (
            <div className="tp-note">Loading…</div>
          ) : (
            <table className="tp-tt-table">
              <thead>
                <tr>
                  <th className="tp-tt-th tp-tt-th--period">Period</th>
                  {data.weekdays.map((w) => <th key={w} className="tp-tt-th">{w}</th>)}
                </tr>
              </thead>
              <tbody className="tp-tt-body">
                {data.rows.map((row, ri) =>
                  row.is_break ? (
                    <tr key={ri}>
                      <td colSpan={data.weekdays.length + 1} className="tp-tt-cellwrap">
                        <div className="tp-tt-break">{row.label}</div>
                      </td>
                    </tr>
                  ) : (
                    <tr key={ri}>
                      <td className="tp-tt-period">{row.label}</td>
                      {row.cells.map((c, ci) => (
                        <td key={ci} className="tp-tt-cellwrap">
                          <div className={cellClass(c)}>{c ? c.name : "—"}</div>
                        </td>
                      ))}
                    </tr>
                  )
                )}
              </tbody>
            </table>
          )}

          <div className="tp-tt-legend">
            <TTLegend swatch="plan" label={subjectLabel || "This subject"} />
            <TTLegend swatch="other" label="Other subjects" />
            <TTLegend swatch="free" label="Free period" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ================= MAIN COMPONENT =================
export default function TeacherTeachingPlan() {
  const [open, setOpen] = useState(false);

  const [subjects, setSubjects] = useState(DEMO_SUBJECTS);
  const [sems, setSems] = useState(DEMO_SEMS);

  // null = show the panel; an id = show the form for that subject
  const [subjectId, setSubjectId] = useState(null);
  const [semSel, setSemSel] = useState(DEMO_SEMS[0]);

  const [allDays, setAllDays] = useState([]);
  const [allotted, setAllotted] = useState(0);
  const [savedUnits, setSavedUnits] = useState([]);     // COURSE PLAN: the saved sessions
  const [planId, setPlanId] = useState(null);            // COURSE PLAN (Part B): for planned vs delivered
  const [showTT, setShowTT] = useState(false);

  const [subjStatus, setSubjStatus] = useState([]);
  const [curStatus, setCurStatus] = useState(null);

  const locked = LOCKED_STATUSES.includes(curStatus);

  const subjectLabel = subjects.find((s) => String(s.id) === String(subjectId))?.label
    || subjStatus.find((s) => String(s.subject_id) === String(subjectId))?.subject
    || "";

  // The class is a PROPERTY OF THE SUBJECT'S TIMETABLE ASSIGNMENT — never a free
  // choice. It used to be a dropdown defaulting to classes[0], with no link to the
  // selected subject, so a teacher could save a plan against a class they don't
  // teach that subject to. The student view matches on this exact string, so the
  // plan then rendered for nobody — no error, just an empty page.
  const classForSubject =
    subjStatus.find((s) => String(s.subject_id) === String(subjectId))?.class_label || "";

  // options (subjects / semesters) — do NOT auto-select a subject
  useEffect(() => {
    API.get("teaching-plans/options/")
      .then((res) => {
        if (res.data?.subjects?.length) setSubjects(res.data.subjects);
        if (res.data?.semesters?.length) { setSems(res.data.semesters); setSemSel(res.data.semesters[0]); }
      })
      .catch(() => {});
  }, []);

  const loadStatus = () => {
    API.get("teaching-plans/subject_status/")
      .then((res) => setSubjStatus(res.data?.subjects || []))
      .catch(() => setSubjStatus([]));
  };
  useEffect(() => { loadStatus(); }, []);

  useEffect(() => {
    const s = subjStatus.find((x) => String(x.subject_id) === String(subjectId));
    setCurStatus(s ? s.status : null);
  }, [subjStatus, subjectId]);

  const subjectLabelFor = (id) =>
    (subjStatus.find((s) => String(s.subject_id) === String(id))?.subject) || "";

  // when a subject is chosen, load its class days + any saved plan.
  // CoursePlanEditor matches saved sessions to timetable sessions by date + period
  // (never by position, which shifts as soon as a holiday is added).
  const loadPlan = () => {
    if (!subjectId || String(subjectId).startsWith("demo")) return;
    API.get(`teaching-plans/class_days/?subject=${subjectId}`)
      .then(async (res) => {
        const days = Array.isArray(res.data?.days) ? res.data.days : [];
        let units = [];
        let id = null;
        try {
          const mine = await API.get("teaching-plans/my/");
          const plan = (mine.data || []).find(
            (p) => String(p.subject_id ?? p.subject) === String(subjectId) ||
                   p.subject === subjectLabelFor(subjectId)
          );
          if (plan && Array.isArray(plan.units)) units = plan.units;
          if (plan) id = plan.id;
        } catch { /* none saved */ }
        setAllotted(res.data?.allotted || 0);
        setAllDays(days);
        setSavedUnits(units);
        setPlanId(id);
      })
      .catch(() => { setAllotted(0); setAllDays([]); setSavedUnits([]); setPlanId(null); });
  };
  useEffect(() => {
    setSavedUnits([]);
    setAllDays([]);
    setPlanId(null);
    loadPlan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subjectId]);

  const counts = subjStatus.reduce((a, s) => { a[s.status] = (a[s.status] || 0) + 1; return a; }, {});

  const openSubject = (id) => {
    setSubjectId(id); window.scrollTo(0, 0);
    // FIX #36: show the subject's own semester
    const s = subjStatus.find((x) => String(x.subject_id) === String(id));
    if (s?.semester_label) setSemSel(s.semester_label);
  };
  const backToPanel = () => { setSubjectId(null); window.scrollTo(0, 0); };

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            <h1 className="tp-title">Teaching plan</h1>
            <p className="tp-subtitle">
              {subjectId
                ? (locked
                    ? "This plan has been submitted. You can view it, but not edit it."
                    : "Plan every timetable session: unit, topic and how you will teach it. Then send it to your HOD.")
                : "Your subjects at a glance. Pick one to write or edit its plan."}
            </p>

            {/* ========== PANEL (shown when no subject is selected) ========== */}
            {!subjectId && (
              subjStatus.length > 0 ? (
                <div className="tp-w920">
                  <div className="tp-count-grid">
                    <CountBox n={counts.approved || 0}    label="Approved"    variant="teal" />
                    <CountBox n={counts.submitted || 0}   label="Submitted"   variant="blue" />
                    <CountBox n={(counts.draft || 0) + (counts.rejected || 0)} label="Draft" variant="amber" />
                    <CountBox n={counts.not_started || 0} label="Not started" variant="grey" />
                  </div>

                  <div className="tp-subj-list">
                    {subjStatus.map((s) => {
                      const m = STATUS_META[s.status] || STATUS_META.not_started;
                      return (
                        <div className="tp-subj-row" key={s.subject_id} onClick={() => openSubject(s.subject_id)}>
                          <div className={`tp-subj-bar ${m.bar}`} />
                          <div className="tp-subj-main">
                            <div className="tp-subj-name">{s.subject}</div>
                            <div className="tp-subj-meta">
                              {s.class_label}
                              {s.allotted_hours ? ` · ${s.planned_hours} / ${s.allotted_hours} hrs`
                                                : s.status === "not_started" ? " · no plan yet" : ""}
                            </div>
                          </div>
                          <span className={`tp-chip ${m.tint}`}>{m.label}</span>
                          <button className="tp-btn-primary"
                            onClick={(e) => { e.stopPropagation(); openSubject(s.subject_id); }}>
                            {m.action}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="tp-panel-note">
                  No subjects assigned to you yet. Ask the admin to add your teaching assignments.
                </div>
              )
            )}

            {/* ========== FORM (shown only after a subject is chosen) ========== */}
            {subjectId && (
              <div className="tp-form-card">
                <button className="tp-back-btn tp-mb14" onClick={backToPanel}>
                  ← Back to my subjects
                </button>

                <div className="tp-form-head">
                  <div className="tp-form-title">Teaching plan · {subjectLabel}</div>
                  <button className="tp-link-btn" onClick={() => setShowTT(true)}>▦ View timetable</button>
                </div>

                {curStatus && curStatus !== "not_started" && (
                  <div className={`tp-banner ${(STATUS_META[curStatus] || {}).tint || ""}`}>
                    {curStatus === "submitted" && "Submitted · waiting for HOD review."}
                    {curStatus === "approved" && "Approved by HOD · published to the class."}
                    {curStatus === "draft" && "Draft · not submitted yet. Continue where you left off."}
                    {curStatus === "rejected" && "Sent back by HOD · please revise and resubmit."}
                  </div>
                )}

                {!locked && (
                  <div className="tp-hint">
                    Every session from your timetable is listed. Click Plan or Edit on a row; each Save keeps your plan as a draft. Holidays are skipped automatically.
                  </div>
                )}

                <div className="tp-field-grid-2">
                  <Field label="Subject">
                    <select className="tp-input" value={subjectId} onChange={(e) => {
                                          setSubjectId(e.target.value);
                                          // FIX #36: show the subject's own semester
                                          const s = subjStatus.find((x) => String(x.subject_id) === String(e.target.value));
                                          if (s?.semester_label) setSemSel(s.semester_label);
                                        }}>
                      {subjStatus.length
                        ? subjStatus.map((s) => <option key={s.subject_id} value={s.subject_id}>{s.subject}</option>)
                        : subjects.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                    </select>
                  </Field>
                  <Field label="Class (from your timetable)">
                    <input className="tp-input tp-input--readonly" readOnly value={classForSubject || "—"} />
                  </Field>
                </div>
                <div className="tp-field-grid-2 tp-mb18">
                  <Field label="Semester">
                    <select className="tp-input" value={semSel} disabled={locked}
                      onChange={(e) => setSemSel(e.target.value)}>
                      {sems.map((s) => <option key={s}>{s}</option>)}
                    </select>
                  </Field>
                  <Field label="Allotted hours (from timetable)">
                    <input className="tp-input tp-input--readonly" readOnly value={`${allotted} hrs`} />
                  </Field>
                </div>

                {/* ===== COURSE PLAN (Part A): sessions table / calendar / counts ===== */}
                <CoursePlanEditor
                  subjectId={subjectId}
                  classForSubject={classForSubject}
                  semSel={semSel}
                  locked={locked}
                  allDays={allDays}
                  allotted={allotted}
                  savedUnits={savedUnits}
                  planId={planId}
                  onReload={loadPlan}
                  onSaved={() => { loadStatus(); if (!planId) loadPlan(); }}
                />
              </div>
            )}

          </div>
        </div>
      </div>

      {showTT && <TimetablePanel subjectLabel={subjectLabel} subjectId={subjectId} onClose={() => setShowTT(false)} />}
    </div>
  );
}