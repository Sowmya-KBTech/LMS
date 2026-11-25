// Frontend/src/features/teachingplan/TeachingPlanStudent.jsx
//
// Teaching Plan shown as a TAB inside the student subject page.
// The subject is already fixed by the parent (teaching-assignment id),
// so this component has NO list view, NO dropdown, NO page chrome —
// it just finds THIS subject's approved plan inside the class-wide list
// and renders its detail.

import React, { useEffect, useState } from "react";
import API from "../../api";
import "../../styles/TeachingPlans.css";

const PREVIEW_COUNT = 6;

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const fmt = (iso) => {
  const [, m, d] = (iso || "").split("-").map(Number);
  return m ? `${MON[m - 1]} ${d}` : iso;
};

// Normalize a label so trivial differences (case, spacing, dash variants)
// never cause a silent "no plan" miss.
const norm = (s) =>
  (s || "")
    .toString()
    .toLowerCase()
    .replace(/[\u2010-\u2015\u2212]/g, "-") // ‐ ‑ ‒ – — ― − → -
    .replace(/\s+/g, " ")
    .trim();

// Pick the one plan (from the whole-class list) that belongs to THIS subject.
// Strategy order, most stable first:
//   1) subject code   (used only if the teaching-assignment exposes one)
//   2) subject id     (used only if both sides carry one)
//   3) normalized name (always available fallback)
function findPlan(plans, ta) {
  if (!ta || !Array.isArray(plans)) return null;

  const taCode = ta.subject_code || ta.code || ta.subjectCode;
  if (taCode) {
    const byCode = plans.find((p) => p.code && norm(p.code) === norm(taCode));
    if (byCode) return byCode;
  }

  const taSubId = ta.subject_id != null ? ta.subject_id : ta.subjectId;
  if (taSubId != null) {
    const byId = plans.find(
      (p) => p.subject_id != null && String(p.subject_id) === String(taSubId)
    );
    if (byId) return byId;
  }

  const taName = ta.subject_name || ta.subject;
  if (taName) {
    const byName = plans.find((p) => norm(p.subject) === norm(taName));
    if (byName) return byName;
  }

  return null;
}

function Tile({ label, value }) {
  return (
    <div className="tp-stat">
      <div className="tp-stat-label">{label}</div>
      <div className="tp-stat-value">{value}</div>
    </div>
  );
}

export default function TeachingPlanStudent({ ta }) {
  const [plans, setPlans] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    API.get("teaching-plans/student/")
      .then((res) => setPlans(Array.isArray(res.data) ? res.data : []))
      .catch(() => setPlans([]))
      .finally(() => setLoaded(true));
  }, []);

  if (!loaded) {
    return <div className="tp-loading">Loading…</div>;
  }

  const sel = findPlan(plans, ta);

  // No approved plan for this subject yet.
  if (!sel) {
    return (
      <div className="tp-empty-box">
        <div className="tp-empty-icon">⏳</div>
        <div className="tp-empty-title">No plan published yet</div>
        <div className="tp-empty-text">
          Your teacher's plan for this subject is still being reviewed. It'll
          appear here once the HOD approves it.
        </div>
      </div>
    );
  }

  const units = sel.units || [];
  const shown = showAll ? units : units.slice(0, PREVIEW_COUNT);
  const hidden = units.length - shown.length;
  const totalHours =
    sel.allotted || units.reduce((a, u) => a + (Number(u.hours) || 0), 0);

  return (
    <div className="tp-card tp-w820">

      {/* HEAD */}
      <div className="tp-plan-head">
        <div className="tp-avatar tp-avatar--md tp-tint--blue">
          {(sel.subject || "?").slice(0, 2).toUpperCase()}
        </div>
        <div className="tp-review-head-info">
          <div className="tp-plan-subject">
            {sel.subject}{sel.code ? ` – ${sel.code}` : ""}
          </div>
          <div className="tp-plan-meta">
            Taught by {sel.teacher}{sel.cls ? ` · ${sel.cls}` : ""}
          </div>
        </div>
        <span className="tp-badge tp-tint--green">✓ Published</span>
      </div>

      {/* STATS */}
      <div className="tp-stats">
        <Tile label="Total topics" value={`${units.length}`} />
        <Tile label="Total hours" value={`${totalHours}`} />
      </div>

      {/* UNITS */}
      <div className="tp-units">
        <div className="tp-section-title">What you'll learn this semester</div>

        <div className={`tp-units-list${showAll ? " tp-units-list--scroll" : ""}`}>
          {shown.map((u, i) => (
            <div className="tp-unit" key={i}>
              <div className="tp-unit-idx">{i + 1}</div>
              <div className="tp-unit-topic">
                {u.topic}
                {/* COURSE PLAN: which unit, and whether it is a lecture, lab or tutorial */}
                {(u.unit_no || u.mode_label) && (
                  <div className="tp-unit-sub">{[u.unit_no ? `Unit ${u.unit_no}` : "", u.mode_label].filter(Boolean).join(" · ")}</div>
                )}
              </div>
              <div className="tp-unit-meta">{u.due ? fmt(u.due) : ""}</div>
            </div>
          ))}
        </div>

        {units.length > PREVIEW_COUNT && (
          <div className="tp-units-toggle" onClick={() => setShowAll((v) => !v)}>
            {showAll ? "Show fewer" : `Show all ${units.length} topics (${hidden} more)`}
          </div>
        )}
      </div>

    </div>
  );
}