// frontend/src/features/mentoring/HodMentorDashboard.jsx
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import MentoringTabs from "./MentoringTabs";

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

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />

      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">
          <div className="content">

            <div className="header-box">
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <h2 style={{ margin: 0 }}>Mentor Allocation Dashboard</h2>
                {data?.department?.name && (
                  <span className="ma-pill ma-blue">{data.department.name}</span>
                )}
              </div>
              <p>Where your department stands, and what is waiting on you</p>
            </div>

            <MentoringTabs />

            {error && (
              <div className="ma-note red" style={{ marginBottom: 16 }}>
                <b>Could not load</b>
                {error}
              </div>
            )}

            {loading && (
              <div className="ma-panel"><div className="ma-empty">Loading…</div></div>
            )}

            {!loading && data && (
              <>
                {/* ================= CONTEXT ================= */}
                <div className="ma-context">
                  <div>
                    <span className="ma-label">Academic Year</span>
                    <select
                      value={academicYear}
                      onChange={(e) => setAcademicYear(e.target.value)}
                    >
                      {(data.academic_year_choices || []).map((ay) => (
                        <option key={ay} value={ay}>{prettyYear(ay)}</option>
                      ))}
                    </select>
                  </div>
                  <div className="ma-spacer" />
                  <button
                    className="ma-btn primary"
                    onClick={() => navigate("/hod/mentor-allocation")}
                  >
                    Open allocations
                  </button>
                </div>

                {/* ================= CARDS ================= */}
                <div className="ma-cards">
                  <div className="ma-card">
                    <div className="l">Total Mentors</div>
                    <div className="n">{cards.total_mentors}</div>
                    <div className="d">{data.department?.name}</div>
                  </div>
                  <div className="ma-card">
                    <div className="l">Total Students</div>
                    <div className="n">{cards.total_students}</div>
                    <div className="d">{prettyYear(data.academic_year)}</div>
                  </div>
                  <div className="ma-card">
                    <div className="l">Active Allocations</div>
                    <div className="n green">{cards.active_allocations}</div>
                    <div className="d">
                      {cards.total_students
                        ? Math.round(
                            (cards.active_allocations / cards.total_students) * 100
                          )
                        : 0}
                      % of students
                    </div>
                  </div>
                  <div className="ma-card">
                    <div className="l">Awaiting Approval</div>
                    <div className="n amber">{cards.pending_allocations}</div>
                    <div className="d">
                      {cards.pending_allocations
                        ? "Advisor proposals"
                        : "Nothing pending"}
                    </div>
                  </div>
                </div>

                {/* ================= WAITING + ADVISORS ================= */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                  <div className="ma-panel">
                    <div className="ma-panel-head">
                      <div>
                        <h3>Waiting on you</h3>
                        <p>Nothing here moves until you act</p>
                      </div>
                    </div>
                    <div className="ma-scroll">
                      <table className="ma-table">
                        <thead>
                          <tr><th>What</th><th>Count</th><th></th></tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td><b>Advisor proposals to approve</b></td>
                            <td>
                              <span className={`ma-pill ${waiting.advisor_proposals ? "ma-amber" : "ma-green"}`}>
                                {waiting.advisor_proposals}
                              </span>
                            </td>
                            <td className="ma-right">
                              {waiting.advisor_proposals ? (
                                <button
                                  className="ma-btn small primary"
                                  onClick={() => navigate("/hod/mentor-allocation")}
                                >
                                  Open
                                </button>
                              ) : (
                                <span style={{ fontSize: 12, color: "#6b7280" }}>Clear</span>
                              )}
                            </td>
                          </tr>
                          <tr>
                            <td><b>Students with no mentor</b></td>
                            <td>
                              <span className={`ma-pill ${waiting.students_without_mentor ? "ma-amber" : "ma-green"}`}>
                                {waiting.students_without_mentor}
                              </span>
                            </td>
                            <td className="ma-right">
                              {waiting.students_without_mentor ? (
                                <button
                                  className="ma-btn small primary"
                                  onClick={() => navigate("/hod/mentor-allocation")}
                                >
                                  Open
                                </button>
                              ) : (
                                <span style={{ fontSize: 12, color: "#6b7280" }}>Clear</span>
                              )}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                    <div className="ma-panel-foot">
                      Class advisors do the groundwork. These are the decisions only
                      you can make.
                    </div>
                  </div>

                  <div className="ma-panel">
                    <div className="ma-panel-head">
                      <div>
                        <h3>Proposals by class advisor</h3>
                        <p>Group lists submitted for your approval</p>
                      </div>
                    </div>
                    <div className="ma-scroll">
                      <table className="ma-table">
                        <thead>
                          <tr>
                            <th>Class advisor</th>
                            <th>Proposed</th>
                            <th>Approved</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {(data.advisor_proposals || []).length === 0 && (
                            <tr>
                              <td colSpan={4} className="ma-empty">
                                No advisor has proposed a group list yet.
                              </td>
                            </tr>
                          )}
                          {(data.advisor_proposals || []).map((a) => (
                            <tr key={a.advisor_id}>
                              <td><b>{a.advisor_name}</b></td>
                              <td className="num">{a.proposed}</td>
                              <td className="num">{a.approved}</td>
                              <td className="ma-right">
                                <span className={`ma-pill ${a.waiting ? "ma-amber" : "ma-green"}`}>
                                  {a.waiting ? `${a.waiting} waiting` : "All approved"}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="ma-panel-foot">
                      An advisor proposes the group list for their own class only.
                    </div>
                  </div>
                </div>

                {/* ================= RECENT CHANGES ================= */}
                <div className="ma-panel" style={{ marginTop: 16 }}>
                  <div className="ma-panel-head">
                    <div>
                      <h3>Recently changed allocations</h3>
                      <p>The last six changes, whoever made them</p>
                    </div>
                    <div style={{ flex: 1 }} />
                    <button
                      className="ma-btn"
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
                          <th>Old mentor</th>
                          <th></th>
                          <th>New mentor</th>
                          <th>Reason</th>
                          <th>Recommended by</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(data.recent_changes || []).length === 0 && (
                          <tr>
                            <td colSpan={7} className="ma-empty">
                              No changes yet this academic year.
                            </td>
                          </tr>
                        )}
                        {(data.recent_changes || []).map((r) => (
                          <tr key={r.id}>
                            <td style={{ whiteSpace: "nowrap", fontSize: 12 }}>
                              {onDate(r.updated_at)}
                            </td>
                            <td><b>{r.student_name}</b></td>
                            <td style={{ fontSize: 12, color: "#6b7280" }}>
                              {r.previous_mentor_name || "—"}
                            </td>
                            <td style={{ color: "#9ca3af" }}>→</td>
                            <td style={{ fontSize: 12 }}><b>{r.mentor_name}</b></td>
                            <td style={{ fontSize: 12, color: "#6b7280" }}>{r.reason || "—"}</td>
                            <td style={{ fontSize: 12, color: "#6b7280" }}>
                              {r.recommended_by || "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="ma-panel-foot">
                    Every approve, reassign and removal lands here as it happens.
                  </div>
                </div>

                {/* ================= MENTOR CAPACITY ================= */}
                <div className="ma-panel" style={{ marginTop: 16 }}>
                  <div className="ma-panel-head">
                    <div>
                      <h3>Mentor capacity</h3>
                      <p>Click a mentor to open their group</p>
                    </div>
                    <div style={{ flex: 1 }} />
                    <span className={`ma-pill ${needsAttention ? "ma-amber" : "ma-green"}`}>
                      {needsAttention ? `${needsAttention} need attention` : "All balanced"}
                    </span>
                  </div>
                  <div className="ma-scroll">
                    <table className="ma-table">
                      <thead>
                        <tr>
                          <th>Mentor</th>
                          <th>Capacity</th>
                          <th>Assigned</th>
                          <th>Available</th>
                          <th>A</th>
                          <th>B</th>
                          <th>C</th>
                          <th>Balance</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {mentors.map((m) => (
                          <tr key={m.id}>
                            <td><b>{m.name}</b></td>
                            <td className="num">{m.capacity}</td>
                            <td className="num">{m.assigned}</td>
                            <td>
                              <span
                                className={`ma-pill ${
                                  m.is_full ? "ma-red" : m.available <= 3 ? "ma-amber" : "ma-green"
                                }`}
                              >
                                {m.is_full ? "Full" : m.available}
                              </span>
                            </td>
                            <td className="num">{m.band_a}</td>
                            <td className="num">{m.band_b}</td>
                            <td className="num">{m.band_c}</td>
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
                                View group
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}