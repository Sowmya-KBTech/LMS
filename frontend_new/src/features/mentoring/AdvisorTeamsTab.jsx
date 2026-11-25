// frontend/src/features/mentoring/AdvisorTeamsTab.jsx
import { useCallback, useEffect, useState } from "react";

import {
  autoFillTeams,
  bandClass,
  closeFormation,
  errorText,
  getAdvisorTeams,
  leaveUnplaced,
  placeStudent,
  prettyYear,
  yearLabel,
} from "./teamApi";

export default function AdvisorTeamsTab() {
  const [data, setData] = useState(null);
  const [picks, setPicks] = useState({});      // student_id -> team_id
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  const flash = (m) => {
    setToast(m);
    setTimeout(() => setToast(""), 4000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const d = await getAdvisorTeams();
      setData(d);
      const seed = {};
      (d.unplaced_students || []).forEach((s) => {
        if (s.options.length) seed[s.student_id] = s.options[0].team_id;
      });
      setPicks(seed);
    } catch (err) {
      setError(errorText(err, "Could not load your class."));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const doPlace = async (studentId) => {
    const teamId = picks[studentId];
    if (!teamId) return;
    setBusy(true);
    try {
      const d = await placeStudent(studentId, teamId);
      flash(d.detail);
      await load();
    } catch (err) {
      flash(errorText(err, "Could not place that student."));
    } finally {
      setBusy(false);
    }
  };

    const doLeave = async (studentId, name) => {
    if (!window.confirm(
      `Leave ${name} out of a team? They will have no mentor this year. ` +
      `You can still place them until formation closes.`
    )) return;
    setBusy(true);
    try {
      const d = await leaveUnplaced(studentId);
      flash(d.detail);
      await load();
    } catch (err) {
      flash(errorText(err, "Could not mark that student."));
    } finally {
      setBusy(false);
    }
  };

  const doAutoFill = async () => {
    setBusy(true);
    try {
      const d = await autoFillTeams();
      flash(d.detail);
      await load();
    } catch (err) {
      flash(errorText(err, "Could not auto-fill."));
    } finally {
      setBusy(false);
    }
  };

  const doClose = async () => {
    setBusy(true);
    try {
      const d = await closeFormation();
      flash(d.detail);
      await load();
    } catch (err) {
      flash(errorText(err, "Could not close formation."));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="ma-panel"><div className="ma-empty">Loading…</div></div>;
  }
  if (error) {
    return <div className="ma-note red"><b>Could not load</b>{error}</div>;
  }
  if (!data) return null;

  const c = data.cards;
  const unplaced = data.unplaced_students;

  return (
    <>
      <div className="ma-note blue">
        <b>
          {data.formation_closed
            ? "Team formation is closed"
            : `${data.class.course_name} · ${yearLabel(data.class.year)} Year · ${prettyYear(data.academic_year)}`}
        </b>
        {data.formation_closed
          ? "Students can no longer join or leave. Pick a mentor for each team on the Mentors tab."
          : `Teams hold ${data.rule.team_size} students, one from each grade band. When a band runs out: ${data.rule.fallback_label.toLowerCase()}.`}
      </div>

      <div className="ma-cards">
        <div className="ma-card">
          <div className="l">Students</div>
          <div className="n">{c.students}</div>
          <div className="d">In your class</div>
        </div>
        <div className="ma-card">
          <div className="l">Teams</div>
          <div className="n">{c.teams_formed}</div>
          <div className="d">Of {c.teams_expected} from class size</div>
        </div>
        <div className="ma-card">
          <div className="l">Complete</div>
          <div className="n green">{c.complete_teams}</div>
          <div className="d">{c.incomplete_teams} still short</div>
        </div>
        <div className="ma-card">
          <div className="l">Not in a team</div>
          <div className={`n${c.unplaced ? " red" : ""}`}>{c.unplaced}</div>
          <div className="d">{c.unplaced ? "Waiting on you" : "Everyone is placed"}</div>
        </div>
      </div>

      {/* ---------- band supply ---------- */}
      <div className="ma-panel">
        <div className="ma-panel-head">
          <div>
            <h3>Band supply</h3>
            <p>Each team needs one of each band — this is what you actually have</p>
          </div>
        </div>
        <div className="tm-supply">
          {data.band_supply.bands.map((b) => (
            <div key={b.band} className={`tm-sup${b.short ? " short" : ""}`}>
              <div className="tm-sup-top">
                <span className={bandClass(b.band)}>{b.band}</span>
                <b>{b.have}</b>
                <i>of {b.needed} needed</i>
                <span className={`ma-pill ${b.short ? "ma-amber" : "ma-green"}`}>
                  {b.short ? `${b.short} short` : b.spare ? `${b.spare} spare` : "exact"}
                </span>
              </div>
              <div className="tm-bar">
                <span style={{
                  width: `${Math.min(100, (b.have / Math.max(1, b.needed)) * 100)}%`,
                }} />
              </div>
            </div>
          ))}
        </div>
        {data.band_supply.unbanded > 0 && (
          <div className="ma-panel-foot">
            {data.band_supply.unbanded} student(s) have no published result yet,
            so they have no band.
          </div>
        )}
      </div>

      {/* ---------- unplaced ---------- */}
      <div className="ma-panel">
        <div className="ma-panel-head">
          <div>
            <h3>Students without a team</h3>
            <p>The list only offers teams this student is allowed to join</p>
          </div>
          <div style={{ flex: 1 }} />
          {unplaced.length > 0 && !data.formation_closed && (
            <button className="ma-btn" disabled={busy} onClick={doAutoFill}>
              Auto-fill all {unplaced.length}
            </button>
          )}
        </div>

        {unplaced.length === 0 ? (
          <div className="ma-empty">
            <b style={{ display: "block", marginBottom: 5 }}>Everyone has a team</b>
            {data.formation_closed
              ? "Formation is closed."
              : "Close formation to lock the teams, then pick mentors."}
          </div>
        ) : (
          <table className="ma-table">
            <thead>
              <tr>
                <th>Student</th><th>Register no</th><th>Band</th>
                <th>CGPA</th><th>Place into</th><th />
              </tr>
            </thead>
            <tbody>
              {unplaced.map((s) => (
                <tr key={s.student_id} className={s.left_unplaced ? "tm-left-out" : ""}>
                  <td>
                    <b>{s.name}</b>
                    <div className="tm-reason">
                      {s.left_unplaced ? "Left unplaced" : "Reason"}: {s.reason}
                    </div>
                  </td>
                  <td>{s.roll_number}</td>
                  <td><span className={bandClass(s.band)}>{s.band || "—"}</span></td>
                  <td>{s.cgpa ?? "—"}</td>
                  <td>
                    {s.left_unplaced ? (
                      <span className="ma-pill ma-grey">
                        No team{s.marked_by ? ` · by ${s.marked_by}` : ""}
                      </span>
                    ) : s.options.length === 0 ? (
                      <span className="ma-pill ma-amber">No team can take them</span>
                    ) : (
                      <select
                        value={picks[s.student_id] || ""}
                        onChange={(e) =>
                          setPicks({ ...picks, [s.student_id]: Number(e.target.value) })
                        }
                      >
                        {s.options.map((o) => (
                          <option key={o.team_id} value={o.team_id}>{o.label}</option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td className="ma-right">
                    <div className="ma-actions">
                      <button className="ma-btn small"
                              disabled={busy || !s.options.length || data.formation_closed}
                              onClick={() => doPlace(s.student_id)}>
                        Place
                      </button>
                      {!s.left_unplaced && data.can_leave_unplaced && !data.formation_closed && (
                        <button className="ma-btn small"
                                disabled={busy}
                                onClick={() => doLeave(s.student_id, s.name)}>
                          Leave unplaced
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="ma-panel-foot">
          <span>
            {data.formation_closed
              ? "Formation is closed — students cannot change team."
              : `${c.unplaced} of ${c.students} still to place`}
          </span>
          <div style={{ flex: 1 }} />
          {!data.formation_closed && (
            <button className="ma-btn primary" disabled={busy || !data.can_close}
                    onClick={doClose}
                    title={data.can_close ? "" : "Place everyone first"}>
              Close formation
            </button>
          )}
        </div>
      </div>

      {/* ---------- teams ---------- */}
      <div className="ma-panel">
        <div className="ma-panel-head">
          <div>
            <h3>Teams</h3>
            <p>{data.teams.length} formed · {c.complete_teams} complete</p>
          </div>
        </div>
        {data.teams.length === 0 ? (
          <div className="ma-empty">No team has been formed yet.</div>
        ) : (
          <div className="tm-grid">
            {data.teams.map((t) => (
              <div key={t.id}
                   className={`tm-team${t.is_complete ? " mine" : ""}`}>
                <div className="tm-team-head">
                  <b>Team {t.number}</b>
                  <div style={{ flex: 1 }} />
                  <span className={`ma-pill ${t.is_complete ? "ma-green" : "ma-amber"}`}>
                    {t.is_complete ? "Complete" : `${t.open_bands.join(", ")} open`}
                  </span>
                </div>
                <div className="tm-slots">
                  {t.members.map((m) => (
                    <div className="tm-slot" key={m.student_id}>
                      <span className={bandClass(m.band)}>{m.band || "—"}</span>
                      <div>
                        <div className="nm">{m.name}</div>
                        <div className="rl">
                          {m.roll_number}{m.is_extra ? " · extra member" : ""}
                        </div>
                      </div>
                    </div>
                  ))}
                  {t.open_bands.map((b) => (
                    <div className="tm-slot open" key={`o-${b}`}>
                      <span className={`${bandClass(b)} ghost`}>{b}</span>
                      <div><div className="nm">Nobody yet</div></div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {toast && <div className="ma-toast">{toast}</div>}
    </>
  );
}