// WAVE 2 - the Principal's college overview (/principal).
//   Principal  : the whole college, department by department (read only)
//   Main admin : the same overview, plus choosing / ending the Principal's term
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import API from "../../api";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { clearRoleFlags } from "../../components/useRoleFlags";
import "../../App.css";
import "../../styles/Reports.css";
import "../../styles/Principal.css";
import HodLeaveApprovals from "./HodLeaveApprovals";   // WAVE 2 Part 1b

const fmtDate = (iso) => {
  if (!iso) return "";
  const [y, m, d] = String(iso).split("-");
  return `${d}-${m}-${y}`;
};
const pct = (p) => (p == null ? "—" : `${Number(p).toFixed(1).replace(/\.0$/, "")}%`);
const tone = (p, good = 75, ok = 60) => (p == null ? "" : p >= good ? "rp-ok" : p >= ok ? "rp-warn" : "rp-bad");
const errorText = (err, fallback) => {
  const d = err?.response?.data;
  return typeof d?.detail === "string" ? d.detail : fallback;
};
const range = (r) => (r.from_date === r.to_date ? fmtDate(r.from_date) : `${fmtDate(r.from_date)} → ${fmtDate(r.to_date)}`);

// ---------------------------------------------------------------- admin: who is Principal
function PrincipalCard({ info, onChanged }) {
  const [candidates, setCandidates] = useState([]);
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    API.get("users/principal/candidates/").then((r) => setCandidates(r.data)).catch(() => setCandidates([]));
  }, []);

  const run = async (fn, ok) => {
    setBusy(true);
    setNotice(null);
    try {
      await fn();
      setPick("");
      clearRoleFlags();
      setNotice({ tone: "ok", text: ok });
      onChanged();
    } catch (err) {
      setNotice({ tone: "bad", text: errorText(err, "That didn't work. Try again.") });
    } finally {
      setBusy(false);
    }
  };

  const assign = () => {
    if (!pick) return setNotice({ tone: "bad", text: "Choose a staff member first." });
    const who = candidates.find((c) => String(c.id) === pick);
    const msg = info.current
      ? `Make ${who?.name} the Principal? ${info.current.name}'s term ends today.`
      : `Make ${who?.name} the Principal?`;
    if (!window.confirm(msg)) return undefined;
    return run(() => API.post("users/principal/assign/", { teacher: pick }), `${who?.name} is now the Principal.`);
  };

  const end = () => {
    if (!window.confirm(`End ${info.current.name}'s term as Principal today?`)) return;
    run(() => API.post("users/principal/end/"), "The Principal's term has ended.");
  };

  return (
    <section className="kb-card">
      <h2 className="kb-at-h2">College Principal</h2>
      {info.current ? (
        <div className="pr-current">
          <div>
            <b>{info.current.name}</b>
            <span className="rp-muted">
              {info.current.department ? `${info.current.department} · ` : ""}since {fmtDate(info.current.start_date)}
            </span>
          </div>
          <button type="button" className="kb-btn kb-btn--sm" onClick={end} disabled={busy}>End term</button>
        </div>
      ) : (
        <p className="rp-muted">No Principal is set. Choose a teaching staff member below.</p>
      )}

      <div className="pr-assign">
        <label className="kb-at-field">
          <span>{info.current ? "Change Principal" : "Choose Principal"}</span>
          <select value={pick} onChange={(e) => setPick(e.target.value)}>
            <option value="">Select a staff member…</option>
            {candidates.filter((c) => c.id !== info.current?.teacher_id).map((c) => (
              <option key={c.id} value={c.id}>{c.name}{c.department ? ` · ${c.department}` : ""}</option>
            ))}
          </select>
        </label>
        <button type="button" className="kb-btn kb-btn--primary" onClick={assign} disabled={busy}>
          {busy ? "Saving…" : "Make Principal"}
        </button>
      </div>
      <p className="rp-muted">
        The Principal keeps their own department and classes. They get the College overview and every class's rank
        list, and are told when an HOD goes on leave.
      </p>

      {notice && (
        <div className={notice.tone === "ok" ? "kb-sa-ok" : "kb-at-error"} role={notice.tone === "ok" ? "status" : "alert"}>
          {notice.text}
        </div>
      )}

      {info.history?.length > 0 && (
        <details className="pr-history">
          <summary>Past Principals ({info.history.length})</summary>
          <ul>
            {info.history.map((h) => (
              <li key={h.id}>{h.name} · {fmtDate(h.start_date)} → {fmtDate(h.end_date)}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- the overview
function Overview({ data }) {
  const t = data.totals;
  return (
    <>
      <div className="rp-stats pr-stats">
        <div className="rp-stat"><span>Students</span><b>{t.students}</b><small>{t.teachers} teaching staff · {t.departments} departments</small></div>
        {data.modules.attendance && (
          <div className="rp-stat">
            <span>Attendance today</span>
            <b className={tone(t.attendance_today.percentage)}>{pct(t.attendance_today.percentage)}</b>
            <small>{t.attendance_today.marked ? `${t.attendance_today.attended} of ${t.attendance_today.marked} hours` : "Not marked yet"}</small>
          </div>
        )}
        {data.modules.attendance && (
          <div className="rp-stat"><span>Below 75% this sem</span><b className={t.low_attendance ? "rp-bad" : ""}>{t.low_attendance}</b><small>students</small></div>
        )}
        {data.modules.leave && (
          <div className="rp-stat"><span>Waiting at HODs</span><b className={t.pending ? "rp-warn" : ""}>{t.pending}</b><small>requests</small></div>
        )}
        {data.modules.leave && (
          <div className="rp-stat"><span>Staff on leave today</span><b>{t.staff_on_leave}</b></div>
        )}
        {data.modules.results && (
          <div className="rp-stat">
            <span>Results pass %</span>
            <b className={tone(t.results.pass_percentage, 80, 60)}>{pct(t.results.pass_percentage)}</b>
            <small>{t.results.appeared ? `${t.results.all_clear} of ${t.results.appeared} all clear` : "None published"}</small>
          </div>
        )}
      </div>

      <section className="kb-card">
        <div className="pr-head">
          <h2 className="kb-at-h2">Departments</h2>
          <Link to="/rank-list" className="kb-btn kb-btn--sm">Rank lists</Link>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table className="rp-table pr-table">
            <thead>
              <tr>
                <th>Department</th><th>HOD</th>
                <th className="num">Students</th><th className="num">Staff</th>
                {data.modules.attendance && <th className="num">Today</th>}
                {data.modules.attendance && <th className="num">&lt; 75%</th>}
                {data.modules.leave && <th className="num">Waiting</th>}
                {data.modules.leave && <th className="num">On leave</th>}
                {data.modules.results && <th className="num">Pass %</th>}
              </tr>
            </thead>
            <tbody>
              {data.departments.length === 0 && (
                <tr><td colSpan={9} className="rp-muted">No departments yet.</td></tr>
              )}
              {data.departments.map((d) => (
                <tr key={d.id}>
                  <td><b>{d.name}</b>{d.code && <span className="rp-muted"> · {d.code}</span>}</td>
                  <td>{d.hod || <span className="rp-bad">Not set</span>}{d.hod_is_acting && <span className="kb-pill warn pr-pill">Acting</span>}</td>
                  <td className="num">{d.students}</td>
                  <td className="num">{d.teachers}</td>
                  {data.modules.attendance && (
                    <td className={`num ${tone(d.attendance_today.percentage)}`}
                      title={d.attendance_today.marked ? `${d.attendance_today.attended} of ${d.attendance_today.marked} hours` : "Not marked yet"}>
                      {pct(d.attendance_today.percentage)}
                    </td>
                  )}
                  {data.modules.attendance && <td className={`num ${d.low_attendance ? "rp-bad" : ""}`}>{d.low_attendance}</td>}
                  {data.modules.leave && (
                    <td className={`num ${d.pending.total ? "rp-warn" : ""}`}
                      title={`On duty ${d.pending.od} · Student leave ${d.pending.student_leave} · Staff leave ${d.pending.staff_leave}`}>
                      {d.pending.total}
                    </td>
                  )}
                  {data.modules.leave && <td className="num">{d.staff_on_leave}</td>}
                  {data.modules.results && (
                    <td className={`num ${tone(d.results.pass_percentage, 80, 60)}`}
                      title={d.results.appeared ? `${d.results.all_clear} of ${d.results.appeared} all clear` : "None published"}>
                      {pct(d.results.pass_percentage)}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="rp-muted pr-note">
          Today = hours marked present or on duty today. Waiting = on-duty, student-leave and staff-leave requests
          waiting for the HOD. Pass % = published semester results with no arrears.
        </p>
      </section>

      {data.modules.leave && (
        <div className="pr-two">
          <section className="kb-card">
            <h2 className="kb-at-h2">Staff on leave today</h2>
            {data.on_leave_today.length === 0 ? <p className="rp-muted">Nobody is on leave today.</p> : (
              <ul className="pr-list">
                {data.on_leave_today.map((r) => (
                  <li key={r.id}>
                    <b>{r.teacher}</b>{r.is_hod && <span className="kb-pill info pr-pill">HOD</span>}
                    <span className="rp-muted">{r.department} · {r.type}{r.session !== "Full day" ? ` · ${r.session}` : ""}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="kb-card">
            <h2 className="kb-at-h2">HOD leave · next 30 days</h2>
            {data.hod_leave_upcoming.length === 0 ? <p className="rp-muted">No HOD leave coming up.</p> : (
              <ul className="pr-list">
                {data.hod_leave_upcoming.map((r) => (
                  <li key={r.id}>
                    <b>{r.teacher}</b>
                    <span className="rp-muted">{r.department} · {range(r)}{r.backup ? ` · backup ${r.backup}` : ""}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </>
  );
}

export default function PrincipalOverview() {
  const [open, setOpen] = useState(false);
  const [info, setInfo] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    API.get("users/principal/").then((r) => setInfo(r.data)).catch(() => setInfo(null));
    API.get("users/principal/dashboard/")
      .then((r) => { setData(r.data); setError(""); })
      .catch((err) => { setData(null); setError(errorText(err, "Couldn't load the college overview.")); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const today = data ? fmtDate(data.today) : "";
  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="header-box">
              <h1>College overview</h1>
              <p>{data ? `All departments at a glance · ${today}` : "The whole college, department by department"}</p>
            </div>

            {info?.can_manage && <PrincipalCard info={info} onChanged={load} />}
            {info?.is_me && data?.modules?.leave && <HodLeaveApprovals />}
            {error && !info?.can_manage && <section className="kb-card"><p className="rp-bad">{error}</p></section>}
            {data && <Overview data={data} />}
          </div>
        </div>
      </div>
    </div>
  );
}
