// frontend/src/features/mentoring/StudentMyTeamTab.jsx
// Content only - no Navbar/Sidebar. Rendered inside StudentMyMentor as a tab.
import { useCallback, useEffect, useState } from "react";

import {
  bandClass,
  errorText,
  getMyTeamPage,
  joinTeam,
  leaveTeam,
  prettyYear,
  yearLabel,
} from "./teamApi";

import "../../styles/TeamAllocation.css";

export default function StudentMyTeamTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // set when the backend refuses because mentoring has not started for this
  // year — an explanation, not a failure
  const [notYet, setNotYet] = useState("");
  const [toast, setToast] = useState("");

  const flash = (m) => {
    setToast(m);
    setTimeout(() => setToast(""), 3500);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getMyTeamPage());
    } catch (err) {
      if (err?.response?.data?.reason === "not_yet_eligible") {
        setNotYet(err.response.data.detail);
      } else {
        setError(errorText(err, "Could not load your team."));
      }
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const doJoin = async (teamId) => {
    setBusy(true);
    try {
      const d = await joinTeam(teamId);
      flash(d.detail);
      await load();
    } catch (err) {
      flash(errorText(err, "Could not join that team."));
    } finally {
      setBusy(false);
    }
  };

  const doLeave = async () => {
    setBusy(true);
    try {
      const d = await leaveTeam();
      flash(d.detail);
      await load();
    } catch (err) {
      flash(errorText(err, "Could not leave your team."));
    } finally {
      setBusy(false);
    }
  };

  const shell = (body) => (
    <>
      {body}
      {toast && <div className="ma-toast">{toast}</div>}
    </>
  );

  if (loading) {
    return shell(
      <div className="ma-panel"><div className="ma-empty">Loading…</div></div>
    );
  }

  // Not an error state. Nothing is wrong and nothing is waiting on them, so
  // no band card, no team count and no Start a new team button.
  if (notYet) {
    return shell(
      <div className="ma-panel" style={{ maxWidth: 620 }}>
        <div className="ma-panel-body" style={{ textAlign: "center", padding: "44px 28px" }}>
          <div style={{ fontSize: 30, opacity: 0.3, marginBottom: 12 }}>◷</div>
          <b style={{ fontSize: 16, display: "block", marginBottom: 8 }}>
            Mentoring has not started for your year
          </b>
          <p style={{ fontSize: 14, color: "#5D5A6B", maxWidth: 420, margin: "0 auto" }}>
            {notYet} There is nothing to do here until then.
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return shell(
      <div className="ma-note red"><b>Could not load</b>{error}</div>
    );
  }
  if (!data) return shell(null);

  const { me, rule, results: teams } = data;
  const myTeam = teams.find((t) => t.is_mine);

  return shell(
    <>
      <div className="ma-note blue">
        <b>
          {data.class.course_name} · {yearLabel(data.class.year)} Year ·{" "}
          {prettyYear(data.academic_year)}
        </b>
        Join a team of {rule.team_size}. Once your class in-charge sends the list
        and the HOD approves it, your mentor appears on the My Mentor tab.
      </div>

      {data.message && (
        <div className={`ma-note ${myTeam ? "" : "amber"}`}>
          <b>
            {myTeam
              ? `You are in Team ${myTeam.number}`
              : data.formation_closed
                ? "Team formation has closed"
                : "All slots for your grade are taken"}
          </b>
          {data.message}
        </div>
      )}

      <div className="ma-cards">
        <div className="ma-card">
          <div className="l">Your band</div>
          <div className="n green">{me.band || "—"}</div>
          <div className="d">{me.cgpa != null ? `CGPA ${me.cgpa}` : "No result yet"}</div>
        </div>
        <div className="ma-card">
          <div className="l">Teams forming</div>
          <div className="n">{data.teams_formed}</div>
          <div className="d">Of {data.teams_expected} for your class</div>
        </div>
        <div className="ma-card">
          <div className="l">Open to you</div>
          <div className="n">{teams.filter((t) => t.can_join).length}</div>
          <div className="d">
            {rule.grade_mix === "abc"
              ? "Matching your grade band"
              : "Any team with room"}
          </div>
        </div>
        <div className="ma-card">
          <div className="l">Your team</div>
          <div className="n">{myTeam ? `#${myTeam.number}` : "—"}</div>
          <div className="d">{myTeam ? "You are placed" : "Not in a team yet"}</div>
        </div>
      </div>

      <div className="ma-panel">
        <div className="ma-panel-head">
          <div>
            <h3>Teams in your class</h3>
            <p>
              {myTeam
                ? "Yours is highlighted. Everyone in a team shares the same mentor."
                : "Only teams you are allowed to join show a button."}
            </p>
          </div>
          <div style={{ flex: 1 }} />
          {data.can_create_team && (
            <button className="ma-btn primary" disabled={busy}
                    onClick={() => doJoin(null)}>
              Start a new team
            </button>
          )}
        </div>

        {teams.length === 0 ? (
          <div className="ma-empty">
            No team has been formed yet.
            {data.can_create_team && " Start the first one."}
          </div>
        ) : (
          <div className="tm-grid">
            {teams.map((t) => (
              <div key={t.id}
                   className={`tm-team${t.is_mine ? " mine" : ""}${
                     t.size >= t.team_size && !t.can_join ? " full" : ""}`}>
                <div className="tm-team-head">
                  <b>Team {t.number}</b>
                  <div style={{ flex: 1 }} />
                  {t.is_mine ? (
                    <span className="ma-pill ma-green">Your team</span>
                  ) : t.can_join ? (
                    <span className="ma-pill ma-amber">
                      {t.would_be_extra ? "Room as an extra" : "Slot open"}
                    </span>
                  ) : (
                    <span className="ma-pill ma-grey">
                      {t.size >= t.team_size ? "Full" : "Not open to you"}
                    </span>
                  )}
                </div>

                <div className="tm-slots">
                  {t.members.map((m) => (
                    <div className="tm-slot" key={m.student_id}>
                      <span className={bandClass(m.band)}>{m.band || "—"}</span>
                      <div>
                        <div className="nm">
                          {m.name}
                          {m.is_me && <span className="tm-you"> you</span>}
                        </div>
                        <div className="rl">
                          {m.roll_number}
                          {m.is_extra ? " · extra member" : ""}
                        </div>
                      </div>
                    </div>
                  ))}

                  {t.open_bands.map((b) => (
                    <div className="tm-slot open" key={`open-${b}`}>
                      <span className={`${bandClass(b)} ghost`}>{b}</span>
                      <div><div className="nm">Nobody yet</div></div>
                    </div>
                  ))}
                </div>

                {!t.is_mine && (
                  t.can_join ? (
                    <button className="ma-btn primary small tm-wide"
                            disabled={busy}
                            onClick={() => doJoin(t.id)}>
                      {t.would_be_extra
                        ? `Join Team ${t.number} as an extra`
                        : `Join Team ${t.number}`}
                    </button>
                  ) : (
                    <button className="ma-btn small tm-wide" disabled
                            title={t.why_not}>
                      {t.why_not || "This team is full"}
                    </button>
                  )
                )}
              </div>
            ))}
          </div>
        )}

        <div className="ma-panel-foot">
          <span>
            {myTeam
              ? data.formation_closed
                ? "Formation has closed — your team is fixed."
                : "You can leave until your class in-charge closes formation."
              : data.formation_closed
                ? "your class in-charge will place you."
                : "If you do not join, your class in-charge places you."}
          </span>
          <div style={{ flex: 1 }} />
          {myTeam && !data.formation_closed && (
            <button className="ma-btn" disabled={busy} onClick={doLeave}>
              Leave this team
            </button>
          )}
        </div>
      </div>
    </>
  );
}
