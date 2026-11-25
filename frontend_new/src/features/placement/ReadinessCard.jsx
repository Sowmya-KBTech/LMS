// ============================================================
// ReadinessCard — a student's placement picture for mentors / tutors
// ============================================================
// Built only from data the college already has (CGPA, arrears,
// attendance, marks verification, drives, offers). Hidden when the
// placement module is switched off for the college.
// ============================================================
import { useEffect, useState } from "react";
import API from "../../api";
import useModules, { hasModule } from "../../components/useModules";

const show = (v, suffix = "") => (v === null || v === undefined || v === "" ? "—" : `${v}${suffix}`);

export default function ReadinessCard({ studentId }) {
  const modules = useModules();
  const enabled = hasModule(modules, "placement");
  // { id, data, failed } for the student last loaded; anything else = loading
  const [result, setResult] = useState({ id: null, data: null, failed: false });

  useEffect(() => {
    if (!enabled || !studentId) return undefined;
    let alive = true;
    API.get(`placement/students/${studentId}/readiness/`)
      .then((r) => alive && setResult({ id: studentId, data: r.data, failed: false }))
      .catch(() => alive && setResult({ id: studentId, data: null, failed: true }));
    return () => { alive = false; };
  }, [studentId, enabled]);

  const current = result.id === studentId;
  const data = current ? result.data : null;
  const failed = current && result.failed;

  if (!enabled || failed) return null;
  if (!data) return <div className="pl-ready"><p className="pl-hint">Loading placement readiness…</p></div>;

  const a = data.academics;
  const d = data.drives;

  return (
    <section className={`pl-ready is-${data.level}`} aria-label="Placement readiness">
      <header className="pl-ready-head">
        <h3>Placement readiness</h3>
        <span className={`pl-level is-${data.level}`}>{data.level_label}</span>
      </header>

      <div className="pl-ready-grid">
        <div><small>CGPA</small><strong>{show(a.cgpa)}</strong></div>
        <div><small>Arrears</small><strong className={a.arrears ? "is-bad" : ""}>{a.arrears}</strong></div>
        <div><small>Attendance</small><strong>{show(a.attendance_percent, "%")}</strong></div>
        <div><small>10th / 12th</small><strong>{show(a.tenth_percent, "%")} / {show(a.twelfth_percent, "%")}</strong></div>
        <div><small>Marks verified</small><strong>{a.marks_verified ? "Yes" : "No"}</strong></div>
      </div>

      <p className="pl-ready-line">
        Drives: applied {d.applied} · attended {d.attended} · rounds cleared {d.rounds_cleared}
        {d.opted_out ? ` · opted out ${d.opted_out}` : ""}
      </p>

      {data.offers.length > 0 && (
        <ul className="pl-ready-offers">
          {data.offers.map((o, i) => (
            <li key={i}>
              {o.company} — {o.role}{o.package_lpa ? ` · ${o.package_lpa} LPA` : ""}
              <span className={`pl-pill is-${o.status}`}>{o.status_display}</span>
            </li>
          ))}
        </ul>
      )}

      {data.flags.length > 0 ? (
        <>
          <p className="pl-ready-sub">Things to work on</p>
          <ul className="pl-flags">
            {data.flags.map((f, i) => <li key={i} className={`is-${f.level}`}>{f.text}</li>)}
          </ul>
        </>
      ) : (
        !data.placed && <p className="pl-ready-line">Nothing blocking — ready for drives.</p>
      )}
    </section>
  );
}
