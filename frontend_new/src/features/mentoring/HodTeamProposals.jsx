// frontend/src/features/mentoring/HodTeamProposals.jsx
import { useCallback, useEffect, useState } from "react";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import MentoringTabs from "./MentoringTabs";

import {
  bandClass,
  decideProposals,
  errorText,
  getMentorRules,
  getTeamProposals,
  prettyYear,
  saveMentorRules,
} from "./teamApi";

import "../../App.css";
import "../../styles/MentorAllocation.css";
import "../../styles/TeamAllocation.css";

export default function HodTeamProposals() {
  const [open, setOpen] = useState(false);

  const [rules, setRules] = useState(null);
  const [props, setProps] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  const [swap, setSwap] = useState({});     // team_id -> mentor_id
  // One note per batch, keyed by batch key. A single shared string put the
  // same reason under every tutor's batch and sent it whichever one you acted
  // on, so a note written for one class was returned to another.
  const [notes, setNotes] = useState({});   // batch key -> note
  const [showRules, setShowRules] = useState(false);

  const flash = (m) => {
    setToast(m);
    setTimeout(() => setToast(""), 4000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [r, p] = await Promise.all([getMentorRules(), getTeamProposals()]);
      setRules(r);
      setProps(p);
      setSwap({});
      setNotes({});
    } catch (err) {
      setError(errorText(err, "Could not load the team proposals."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveRule = async (field, value) => {
    setBusy(true);
    try {
      const d = await saveMentorRules({ [field]: value });
      setRules(d);
      flash("Rules saved.");
    } catch (err) {
      flash(errorText(err, "Could not save that rule."));
    } finally {
      setBusy(false);
    }
  };

  const decide = async (ids, decision, noteText, mentorId) => {
    if (decision === "reject" && !String(noteText || "").trim()) {
      flash("Say why you are returning it - the class in-charge is shown this.");
      return;
    }
    setBusy(true);
    try {
      const d = await decideProposals(ids, decision, noteText, mentorId);
      flash(
        decision === "approve"
          ? `${d.count} student allocation(s) approved.`
          : `${d.count} allocation(s) rejected.`
      );
      await load();
    } catch (err) {
      flash(errorText(err, "Could not record that decision."));
    } finally {
      setBusy(false);
    }
  };

  /**
   * Approve a whole batch, keeping any mentor the HOD changed by hand.
   *
   * decideProposals sends ONE mentor_id for the whole call, so teams with a
   * changed mentor cannot ride along with the rest. They are sent one call
   * each, then everything untouched goes in a single call.
   *
   * This used to be a plain decide(b.allocation_ids, "approve") with no mentor
   * at all: every dropdown change on the screen was thrown away silently and
   * the original proposal was approved instead.
   */
  const approveBatch = async (b) => {
    const changed = b.teams.filter(
      (t) => swap[t.team_id] && swap[t.team_id] !== t.mentor_id
    );
    const untouched = b.teams.filter(
      (t) => !(swap[t.team_id] && swap[t.team_id] !== t.mentor_id)
    );
    const noteText = notes[b.key] || "";

    setBusy(true);
    try {
      let count = 0;
      for (const t of changed) {
        const d = await decideProposals(
          t.allocation_ids, "approve", noteText, swap[t.team_id]
        );
        count += d.count || 0;
      }
      const restIds = untouched.flatMap((t) => t.allocation_ids || []);
      if (restIds.length) {
        const d = await decideProposals(restIds, "approve", noteText);
        count += d.count || 0;
      }
      flash(
        changed.length
          ? `${count} allocation(s) approved · ${changed.length} with your mentor change.`
          : `${count} student allocation(s) approved.`
      );
      await load();
    } catch (err) {
      flash(errorText(err, "Could not record that decision."));
    } finally {
      setBusy(false);
    }
  };

  const shell = (body) => (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="header-box">
              <h2 style={{ margin: 0 }}>Team Proposals</h2>
              <p>
                Team rules for your department, and the lists your class
                class in-charges have sent
                {rules?.academic_year ? ` · ${prettyYear(rules.academic_year)}` : ""}
              </p>
            </div>
            <MentoringTabs />
            {body}
          </div>
        </div>
      </div>
      {toast && <div className="ma-toast">{toast}</div>}
    </div>
  );

  if (loading) {
    return shell(<div className="ma-panel"><div className="ma-empty">Loading…</div></div>);
  }
  if (error) {
    return shell(<div className="ma-note red"><b>Could not load</b>{error}</div>);
  }

  const rule = rules?.rule || {};
  const pool = rules?.mentor_pool || {};
  const c = props?.counts || {};
  const batches = props?.batches || [];
  const mentorOptions = props?.mentor_options || [];

  return shell(
    <>
      {/* ================= TEAM RULES ================= */}
      <div className="ma-panel">
        <div className="ma-panel-head">
          <div>
            <h3>Team rules</h3>
            <p>These run before any class starts forming teams</p>
          </div>
          <div style={{ flex: 1 }} />
          <span className="ma-pill ma-grey">
            {rules?.department?.name} · every class
          </span>
          <button className="ma-btn small" onClick={() => setShowRules(!showRules)}>
            {showRules ? "Hide" : "Change rules"}
          </button>
        </div>

        {!showRules ? (
          <div className="ma-panel-body">
            <div className="ma-note blue">
              <b>
                Teams of {rule.team_size} · {rule.grade_mix_label} ·{" "}
                {pool.eligible} of {pool.total_teachers} teachers eligible
              </b>
              When a band runs out: {(rule.fallback_label || "").toLowerCase()}.
              {pool.held_back_rotation
                ? ` ${pool.held_back_rotation} teacher(s) mentored last year and are held back.`
                : ""}
            </div>
          </div>
        ) : (
          <>
            <div className="tm-rule">
              <div>
                <b>Students per team</b>
                <p>The number of teams comes from this and the class size.</p>
              </div>
              <select value={rule.team_size} disabled={busy}
                      onChange={(e) => saveRule("team_size", Number(e.target.value))}>
                {[2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>

            <div className="tm-rule">
              <div>
                <b>Grade mix</b>
                <p>Checked when a student joins, so an unbalanced team cannot form.</p>
              </div>
              <select value={rule.grade_mix} disabled={busy}
                      onChange={(e) => saveRule("grade_mix", e.target.value)}>
                {(rules?.choices?.grade_mix || []).map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            <div className="tm-rule">
              <div>
                <b>When a band runs out</b>
                <p>Students are told this on their own screen before they try to join.</p>
              </div>
              <select value={rule.fallback} disabled={busy}
                      onChange={(e) => saveRule("fallback", e.target.value)}>
                {(rules?.choices?.fallback || []).map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            <div className="tm-rule">
              <input type="checkbox" checked={rule.skip_last_year_mentors} disabled={busy}
                     onChange={(e) => saveRule("skip_last_year_mentors", e.target.checked)} />
              <div>
                <b>Skip teachers who mentored last year</b>
                <p>
                  Rotation, from last year's allocation records.
                  {pool.held_back_rotation
                    ? ` ${pool.held_back_rotation} of ${pool.total_teachers} held back.`
                    : " Nobody is held back at the moment."}
                </p>
              </div>
            </div>

            <div className="tm-rule">
              <input type="checkbox" checked={rule.skip_class_advisors} disabled={busy}
                     onChange={(e) => saveRule("skip_class_advisors", e.target.checked)} />
              <div>
                <b>Skip class in-charges</b>
                <p>Keeps the class in-charge free for change requests from their own class.</p>
              </div>
            </div>

            <div className="tm-rule">
              <input type="checkbox" checked={rule.tiebreak_fewest_mentees} disabled={busy}
                     onChange={(e) => saveRule("tiebreak_fewest_mentees", e.target.checked)} />
              <div>
                <b>Then order by fewest mentees</b>
                <p>Breaks ties using how many students each teacher already mentors.</p>
              </div>
            </div>
          </>
        )}

        {/* live preview per class */}
        {(rules?.preview || []).length > 0 && (
          <>
            <div className="ma-scroll">
              <table className="ma-table">
                <thead>
                  <tr>
                    <th>Class</th><th>Students</th><th>Bands</th>
                    <th>Teams</th><th>Mentors needed</th><th>Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.preview.map((p) => (
                    <tr key={`${p.course_id}-${p.year}`}>
                      <td><b>{p.course_name}</b> · {p.year_label} Year</td>
                      <td className="num">{p.students}</td>
                      <td>
                        <span className={bandClass("A")}>A</span> {p.band_a}{" · "}
                        <span className={bandClass("B")}>B</span> {p.band_b}{" · "}
                        <span className={bandClass("C")}>C</span> {p.band_c}
                        {p.band_none ? ` · ${p.band_none} unbanded` : ""}
                      </td>
                      <td className="num"><b>{p.teams}</b></td>
                      <td className="num">{p.mentors_needed}</td>
                      <td>
                        {p.fully_balanced ? (
                          <span className="ma-pill ma-green">Balanced</span>
                        ) : (
                          <span className="ma-pill ma-amber">
                            {Object.entries(p.short_of)
                              .map(([b, n]) => `${n} short of ${b}`)
                              .join(" · ")}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="ma-panel-foot">
              Team counts are worked out from class size — never a fixed number.
            </div>
          </>
        )}
      </div>

      {/* ================= PROPOSALS ================= */}
      {batches.length === 0 ? (
        <div className="ma-panel">
          <div className="ma-empty">
            <b style={{ display: "block", marginBottom: 6 }}>Nothing waiting on you</b>
            No class in-charge has sent a team list. They appear here once sent.
          </div>
        </div>
      ) : (
        <>
          <div className="ma-cards">
            <div className="ma-card">
              <div className="l">Batches</div>
              <div className="n">{c.batches}</div>
              <div className="d">One per class in-charge and class</div>
            </div>
            <div className="ma-card">
              <div className="l">Teams</div>
              <div className="n">{c.teams}</div>
              <div className="d">Waiting on your decision</div>
            </div>
            <div className="ma-card">
              <div className="l">Students</div>
              <div className="n">{c.students}</div>
              <div className="d">Covered by these teams</div>
            </div>
            <div className="ma-card">
              <div className="l">Class in-charge overrode</div>
              <div className={`n${c.overridden ? " amber" : ""}`}>{c.overridden}</div>
              <div className="d">{c.overridden ? "Worth a look first" : "All as suggested"}</div>
            </div>
          </div>

          {batches.map((b) => {
            const note = notes[b.key] || "";
            const changedCount = b.teams.filter(
              (t) => swap[t.team_id] && swap[t.team_id] !== t.mentor_id
            ).length;

            return (
              <div className="ma-panel" key={b.key}>
                <div className="ma-panel-head">
                  <div>
                    <h3>{b.advisor_name}</h3>
                    <p>
                      {b.course_name} · {b.year_label} Year · {b.teams.length} teams ·{" "}
                      {b.students} students
                    </p>
                  </div>
                  <div style={{ flex: 1 }} />
                  {b.overridden > 0 && (
                    <span className="ma-pill ma-amber">
                      {b.overridden} overridden by the class in-charge
                    </span>
                  )}
                  {changedCount > 0 && (
                    <span className="ma-pill ma-blue">
                      {changedCount} mentor change(s) not yet saved
                    </span>
                  )}
                  <button className="ma-btn small danger"
                          disabled={busy || !note.trim()}
                          title={note.trim() ? "" : "Write a reason first"}
                          onClick={() => decide(b.allocation_ids, "reject", note)}>
                    Return to class in-charge
                  </button>
                  <button className="ma-btn primary small" disabled={busy}
                          onClick={() => approveBatch(b)}>
                    Approve all {b.teams.length}
                  </button>
                </div>

                <div className="ma-scroll">
                  <table className="ma-table">
                    <thead>
                      <tr>
                        <th style={{ width: 90 }}>Team</th>
                        <th>Students</th>
                        <th style={{ width: 210 }}>Mentor</th>
                        <th style={{ width: 150 }}>Source</th>
                        <th style={{ width: 110 }} />
                      </tr>
                    </thead>
                    <tbody>
                      {b.teams.map((t) => {
                        // The proposed mentor may not be in mentor_options -
                        // held back by rotation, or over capacity. Without this
                        // the browser falls back to showing the FIRST option, so
                        // the HOD reads a mentor nobody proposed.
                        const selected = swap[t.team_id] ?? t.mentor_id ?? "";
                        const inPool = mentorOptions.some((m) => m.id === selected);

                        return (
                          <tr key={t.team_id}>
                            <td><b>Team {String(t.number).padStart(2, "0")}</b></td>
                            <td>
                              {["a", "b", "c", "unbanded"].flatMap((k) =>
                                (t[k] || []).map((s) => (
                                  <span className="tm-inline" key={s.student_id}>
                                    <span className={bandClass(s.band)}>{s.band || "—"}</span>
                                    {s.name}
                                    {s.is_extra ? " (extra)" : ""}
                                  </span>
                                ))
                              )}
                            </td>
                            <td>
                              <select
                                value={selected}
                                disabled={busy}
                                className={swap[t.team_id] ? "tm-edited" : ""}
                                onChange={(e) =>
                                  setSwap({
                                    ...swap,
                                    [t.team_id]: Number(e.target.value),
                                  })
                                }
                              >
                                {!selected && (
                                  <option value="">No mentor proposed</option>
                                )}
                                {selected && !inPool && (
                                  <option value={selected}>
                                    {t.mentor_name || "Proposed mentor"} · not in the pool
                                  </option>
                                )}
                                {mentorOptions.map((m) => (
                                  <option key={m.id} value={m.id}>
                                    {m.name} · {m.assigned}/{m.capacity}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td>
                              {t.advisor_overrode ? (
                                <span className="ma-pill ma-amber"
                                      title={`Suggested: ${t.suggested_name}`}>
                                  Class in-charge overrode
                                </span>
                              ) : (
                                <span className="ma-pill ma-grey">Suggested</span>
                              )}
                              {t.has_extra && (
                                <span className="ma-pill ma-blue" style={{ marginLeft: 6 }}>
                                  {t.size} students
                                </span>
                              )}
                            </td>
                            <td className="ma-right">
                              <button className="ma-btn small" disabled={busy}
                                      onClick={() =>
                                        decide(
                                          t.allocation_ids, "approve", note,
                                          swap[t.team_id]
                                        )
                                      }>
                                Approve
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="ma-panel-foot">
                  <input
                    placeholder="Reason - required to return, optional to approve"
                    value={note}
                    onChange={(e) =>
                      setNotes({ ...notes, [b.key]: e.target.value })
                    }
                    style={{
                      padding: "9px 11px", border: "1px solid #E7E7EC",
                      borderRadius: 9, minWidth: 280,
                    }}
                  />
                  <div style={{ flex: 1 }} />
                  <span>
                    {note.trim()
                      ? "The class in-charge is shown this note either way."
                      : "Students see a mentor only after you approve."}
                  </span>
                </div>
              </div>
            );
          })}
        </>
      )}
    </>
  );
}
