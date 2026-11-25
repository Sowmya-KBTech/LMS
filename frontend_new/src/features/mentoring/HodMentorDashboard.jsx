// frontend/src/features/mentoring/HodMentorDashboard.jsx
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import MentoringTabs from "./MentoringTabs";
import { HodRecordsSummary } from "./MentoringRecords";   // WAVE 1

import { errorText, getDashboard, prettyYear } from "./mentoringApi";

import "../../App.css";
import "../../styles/MentorAllocation.css";

const onDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
};

export default function HodMentorDashboard() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [academicYear, setAcademicYear] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // the capacity table is reference, not a task
  const [showCapacity, setShowCapacity] = useState(false);

  const load = useCallback(async (ay) => {
    setLoading(true);
    setError("");
    try {
      const d = await getDashboard(ay ? { academic_year: ay } : {});
      setData(d);
      if (!ay) setAcademicYear(d.academic_year);
    } catch (err) {
      setError(errorText(err, "Could not load the dashboard. Are you an HOD?"));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(academicYear);
  }, [academicYear, load]);

  const cards = data?.cards || {};
  const waiting = data?.waiting_on_you || {};
  const mentors = data?.mentors || [];
  const needsAttention = mentors.filter((m) => m.balance_state !== "ok").length;

  const toApprove = waiting.advisor_proposals || 0;
  const noMentor = waiting.students_without_mentor || 0;
  const allClear = !toApprove && !noMentor;

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />

      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">
          <div className="content">

            {/* ================= HEADER =================
                Year picker moved up here. It used to sit in its own bar below
                the tabs, which pushed the actual content a further row down. */}
            <div className="header-box">
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <h2 style={{ margin: 0 }}>Mentoring</h2>
                {data?.department?.name && (
                  <span className="ma-pill ma-blue">{data.department.name}</span>
                )}
                <div style={{ flex: 1 }} />
                {data && (
                  <select
                    value={academicYear}
                    onChange={(e) => setAcademicYear(e.target.value)}
                    style={{ minWidth: 150 }}
                  >
                    {(data.academic_year_choices || []).map((ay) => (
                      <option key={ay} value={ay}>
                        {prettyYear(ay)}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <p>
                Each student is paired with a faculty mentor for the year. Class in-charges
                propose the groups for their own class; you approve them.
              </p>
            </div>

            <MentoringTabs />

            {error && (
              <div className="ma-note red" style={{ marginBottom: 16 }}>
                <b>Could not load</b>
                {error}
              </div>
            )}

            {loading && (
              <div className="ma-panel">
                <div className="ma-empty">Loading…</div>
              </div>
            )}

            {!loading && data && (
              <>
                {/* ================= WHAT NEEDS DOING =================
                    This replaces the old "Waiting on you" panel, which was a
                    two-row table restating numbers already in the cards, with
                    an Open button on each row going to the same page. */}
                {allClear ? (
                  <div className="ma-note" style={{ marginBottom: 16 }}>
                    <b>Nothing waiting on you</b>
                    Every student in {data.department?.name} has a mentor and no
                    proposal is pending.
                  </div>
                ) : (
                  <div className="ma-note amber" style={{ marginBottom: 16 }}>
                    <b>
                      {[
                        toApprove ? `${toApprove} proposal${toApprove === 1 ? "" : "s"} to approve` : null,
                        noMentor ? `${noMentor} student${noMentor === 1 ? "" : "s"} with no mentor` : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </b>
                    Both are handled on the allocation page. Nothing moves until you
                    act on them.
                    <div style={{ marginTop: 10 }}>
                      <button
                        className="ma-btn primary"
                        onClick={() => navigate("/hod/mentor-allocation")}
                      >
                        Open allocations
                      </button>
                    </div>
                  </div>
                )}

                {/* ================= SUMMARY ================= */}
                <div className="ma-cards">
                  <div className="ma-card">
                    <div className="l">Students</div>
                    <div className="n">{cards.total_students}</div>
                    <div className="d">{prettyYear(data.academic_year)}</div>
                  </div>
                  <div className="ma-card">
                    <div className="l">Have a mentor</div>
                    <div className="n green">{cards.active_allocations}</div>
                    <div className="d">
                      {cards.total_students
                        ? Math.round((cards.active_allocations / cards.total_students) * 100)
                        : 0}
                      % of students
                    </div>
                  </div>
                  <div className="ma-card">
                    <div className="l">Awaiting your approval</div>
                    <div className="n">{cards.pending_allocations}</div>
                    <div className="d">
                      {cards.pending_allocations ? "Proposed by a class in-charge" : "Nothing pending"}
                    </div>
                  </div>
                  <div className="ma-card">
                    <div className="l">Mentors available</div>
                    <div className="n">{cards.total_mentors}</div>
                    <div className="d">
                      {needsAttention
                        ? `${needsAttention} with an uneven grade mix`
                        : "All have a balanced mix"}
                    </div>
                  </div>
                </div>

                {/* ================= TUTOR PROPOSALS =================
                    The old layout hard-coded two equal columns, so on a narrow
                    screen both tables squeezed instead of stacking. */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
                    gap: 16,
                  }}
                >
                  <div className="ma-panel">
                    <div className="ma-panel-head">
                      <div>
                        <h3>Proposals by class in-charge</h3>
                        <p>A class in-charge proposes the group list for their own class only</p>
                      </div>
                    </div>
                    <div className="ma-scroll">
                      <table className="ma-table">
                        <thead>
                          <tr>
                            <th>Class in-charge</th>
                            <th>Proposed</th>
                            <th>Approved</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {(data.advisor_proposals || []).length === 0 && (
                            <tr>
                              <td colSpan={4} className="ma-empty">
                                No class in-charge has proposed a group list yet. Until one does,
                                you can assign students yourself from the allocation
                                page.
                              </td>
                            </tr>
                          )}
                          {(data.advisor_proposals || []).map((a) => (
                            <tr key={a.advisor_id}>
                              <td>
                                <b>{a.advisor_name}</b>
                              </td>
                              <td className="num">{a.proposed}</td>
                              <td className="num">{a.approved}</td>
                              <td className="ma-right">
                                <span
                                  className={`ma-pill ${a.waiting ? "ma-amber" : "ma-green"}`}
                                >
                                  {a.waiting ? `${a.waiting} waiting` : "All approved"}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* ================= RECENT CHANGES ================= */}
                  <div className="ma-panel">
                    <div className="ma-panel-head">
                      <div>
                        <h3>Recent changes</h3>
                        <p>The last six, whoever made them</p>
                      </div>
                      <div style={{ flex: 1 }} />
                      <button
                        className="ma-btn small"
                        onClick={() => navigate("/hod/mentor-history")}
                      >
                        Full history
                      </button>
                    </div>
                    <div className="ma-scroll">
                      <table className="ma-table">
                        <thead>
                          <tr>
                            <th>When</th>
                            <th>Student</th>
                            <th>Mentor</th>
                            <th>Why</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(data.recent_changes || []).length === 0 && (
                            <tr>
                              <td colSpan={4} className="ma-empty">
                                No changes yet this academic year.
                              </td>
                            </tr>
                          )}
                          {(data.recent_changes || []).map((r) => (
                            <tr key={r.id}>
                              <td style={{ whiteSpace: "nowrap", fontSize: 13 }}>
                                {onDate(r.updated_at)}
                              </td>
                              <td>
                                <b>{r.student_name}</b>
                              </td>
                              <td style={{ fontSize: 13 }}>
                                {r.previous_mentor_name ? (
                                  <>
                                    <span style={{ color: "#85839A" }}>
                                      {r.previous_mentor_name}
                                    </span>
                                    <span style={{ color: "#85839A" }}> → </span>
                                  </>
                                ) : null}
                                <b>{r.mentor_name}</b>
                              </td>
                              <td style={{ fontSize: 13, color: "#5D5A6B" }}>
                                {r.reason || "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="ma-panel-foot">
                      Every approval, change and removal lands here. Nothing is ever
                      deleted.
                    </div>
                  </div>
                </div>

                {/* ================= MENTOR CAPACITY =================
                    Nine columns of reference data, collapsed by default. */}
                <div className="ma-panel" style={{ marginTop: 16 }}>
                  <div
                    className="ma-panel-head"
                    style={{ cursor: "pointer" }}
                    onClick={() => setShowCapacity((v) => !v)}
                  >
                    <div>
                      <h3>How loaded is each mentor?</h3>
                      <p>
                        {mentors.length} mentor{mentors.length === 1 ? "" : "s"}
                        {needsAttention
                          ? ` · ${needsAttention} could do with a better grade mix`
                          : " · all have a balanced grade mix"}
                      </p>
                    </div>
                    <div style={{ flex: 1 }} />
                    <button className="ma-btn small">
                      {showCapacity ? "Hide" : "Show"}
                    </button>
                  </div>

                  {showCapacity && (
                    <>
                      <div className="ma-scroll">
                        <table className="ma-table">
                          <thead>
                            <tr>
                              <th>Mentor</th>
                              <th>Students</th>
                              <th>Room left</th>
                              <th>Grade mix</th>
                              <th>Is it balanced?</th>
                              <th></th>
                            </tr>
                          </thead>
                          <tbody>
                            {mentors.length === 0 && (
                              <tr>
                                <td colSpan={6} className="ma-empty">
                                  No teacher in this department yet.
                                </td>
                              </tr>
                            )}
                            {mentors.map((m) => (
                              <tr key={m.id}>
                                <td>
                                  <b>{m.name}</b>
                                </td>
                                <td className="num">
                                  {m.assigned} <span style={{ color: "#85839A" }}>of {m.capacity}</span>
                                </td>
                                <td>
                                  <span
                                    className={`ma-pill ${
                                      m.is_full
                                        ? "ma-red"
                                        : m.available <= 3
                                        ? "ma-amber"
                                        : "ma-green"
                                    }`}
                                  >
                                    {m.is_full ? "Full" : `${m.available} free`}
                                  </span>
                                </td>
                                <td style={{ fontSize: 13, color: "#5D5A6B" }}>
                                  A {m.band_a} · B {m.band_b} · C {m.band_c}
                                </td>
                                <td>
                                  <span
                                    className={`ma-pill ${
                                      m.balance_state === "ok"
                                        ? "ma-green"
                                        : m.balance_state === "warn"
                                        ? "ma-amber"
                                        : "ma-red"
                                    }`}
                                  >
                                    {m.balance_message}
                                  </span>
                                </td>
                                <td className="ma-right">
                                  <button
                                    className="ma-btn small"
                                    onClick={() => navigate(`/hod/mentors/${m.id}`)}
                                  >
                                    View students
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <div className="ma-panel-foot">
                        A balanced mentor has a spread of grade A, B and C students
                        rather than all of one kind.
                      </div>
                    </>
                  )}
                </div>

                {/* WAVE 1: mentoring sessions by category */}
                <HodRecordsSummary academicYear={academicYear} />
              </>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}