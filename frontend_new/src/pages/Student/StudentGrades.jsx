import { useEffect, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../styles/Grades.css";

export default function StudentGrades() {
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const [open, setOpen] = useState(false);
  const [submissions, setSubmissions] = useState([]);
  const [quizAttempts, setQuizAttempts] = useState([]);
  const [loading, setLoading] = useState(true);


  const fetchData = async () => {
    try {
      setLoading(true);
      const subRes = await API.get("/submissions/");
      const subData = subRes.data?.results || subRes.data || [];
      setSubmissions(subData.filter((s) => (s.student?.id || s.student) === user.id));

      const quizRes = await API.get("/quiz-attempts/");
      const quizData = quizRes.data?.results || quizRes.data || [];
      setQuizAttempts(quizData.filter((q) => (q.student?.id || q.student) === user.id));
    } catch (err) {
      console.log("Fetch error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const totalAssignmentMarks = submissions.reduce((sum, s) => sum + Number(s.marks || 0), 0);
  const totalAssignmentMax   = submissions.reduce((sum, s) => sum + Number(s.total_marks || 0), 0);
  const totalQuizMarks       = quizAttempts.reduce((sum, q) => sum + Number(q.score || 0), 0);
  const assignmentPct = totalAssignmentMax > 0 ? Math.round((totalAssignmentMarks / totalAssignmentMax) * 100) : 0;

  const statusColor = (status = "") => {
    const s = status.toLowerCase();
    if (s === "graded")   return "grades-badge graded";
    if (s === "submitted") return "grades-badge submitted";
    if (s === "pending")  return "grades-badge pending";
    return "grades-badge";
  };

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="grades-page">

              {/* ── Page Header ── */}
              <div className="grades-header">
                <div>
                  <h1 className="grades-title">My Grades</h1>
                  <p className="grades-subtitle">View assignment and quiz performance</p>
                </div>
              </div>

              {/* ── Stat Cards ── */}
              <div className="grades-stats">

                <div className="grades-stat-card">
                  <div className="grades-stat-icon assign-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                      <polyline points="14 2 14 8 20 8"/>
                      <line x1="16" y1="13" x2="8" y2="13"/>
                      <line x1="16" y1="17" x2="8" y2="17"/>
                    </svg>
                  </div>
                  <div className="grades-stat-info">
                    <span className="grades-stat-label">Assignment Marks</span>
                    <span className="grades-stat-value">
                      {totalAssignmentMax > 0
                        ? <>{totalAssignmentMarks}<span className="grades-stat-max">/{totalAssignmentMax}</span></>
                        : totalAssignmentMarks}
                    </span>
                    {totalAssignmentMax > 0 && (
                      <div className="grades-progress-wrap">
                        <div className="grades-progress-bar">
                          <div className="grades-progress-fill assign-fill" style={{ width: `${assignmentPct}%` }} />
                        </div>
                        <span className="grades-progress-pct">{assignmentPct}%</span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="grades-stat-card">
                  <div className="grades-stat-icon quiz-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10"/>
                      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
                      <line x1="12" y1="17" x2="12.01" y2="17"/>
                    </svg>
                  </div>
                  <div className="grades-stat-info">
                    <span className="grades-stat-label">Quiz Scores</span>
                    <span className="grades-stat-value">{totalQuizMarks}</span>
                    <span className="grades-stat-sub">{quizAttempts.length} attempt{quizAttempts.length !== 1 ? "s" : ""}</span>
                  </div>
                </div>
                 
                </div>
              

              {loading ? (
                <div className="grades-loading">
                  <div className="grades-spinner" />
                  <p>Loading grades…</p>
                </div>
              ) : (
                <>
                  {/* ── Assignment Results ── */}
                  <div className="grades-section">
                    <div className="grades-section-header">
                      <h2 className="grades-section-title">
                        <span className="grades-section-dot assign-dot" />
                        Assignment Results
                      </h2>
                      <span className="grades-count">{submissions.length} total</span>
                    </div>

                    {submissions.length === 0 ? (
                      <div className="grades-empty">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="40" height="40">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                          <polyline points="14 2 14 8 20 8"/>
                        </svg>
                        <p>No assignment submissions yet</p>
                      </div>
                    ) : (
                      <div className="grades-table-wrap">
                        <table className="grades-table">
                          <thead>
                            <tr>
                              <th>Assignment</th>
                              <th>Subject</th>
                              <th>Status</th>
                              <th>Marks</th>
                              <th>Feedback</th>
                            </tr>
                          </thead>
                          <tbody>
                            {submissions.map((s) => (
                              <tr key={s.id}>
                                <td className="grades-td-primary">{s.assignment_title}</td>
                                <td>{s.subject_name}</td>
                                <td><span className={statusColor(s.status)}>{s.status}</span></td>
                                <td className="grades-td-score">
                                  {s.marks !== null ? (
                                    <>
                                      <strong>{s.marks}</strong>
                                      <span className="grades-td-max">/{s.total_marks}</span>
                                    </>
                                  ) : "—"}
                                </td>
                                <td className="grades-td-feedback">{s.feedback || "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  {/* ── Quiz Results ── */}
                  <div className="grades-section">
                    <div className="grades-section-header">
                      <h2 className="grades-section-title">
                        <span className="grades-section-dot quiz-dot" />
                        Quiz Results
                      </h2>
                      <span className="grades-count">{quizAttempts.length} attempt{quizAttempts.length !== 1 ? "s" : ""}</span>
                    </div>

                    {quizAttempts.length === 0 ? (
                      <div className="grades-empty">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="40" height="40">
                          <circle cx="12" cy="12" r="10"/>
                          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
                          <line x1="12" y1="17" x2="12.01" y2="17"/>
                        </svg>
                        <p>No quiz attempts yet</p>
                      </div>
                    ) : (
                      <div className="grades-table-wrap">
                        <table className="grades-table">
                          <thead>
                            <tr>
                              <th>Quiz</th>
                              <th>Score</th>
                              <th>Submitted</th>
                            </tr>
                          </thead>
                          <tbody>
                            {quizAttempts.map((q) => (
                              <tr key={q.id}>
                                <td className="grades-td-primary">{q.quiz_title}</td>
                                <td className="grades-td-score">
                                  <strong>{q.score}</strong>
                                </td>
                                <td className="grades-td-date">
                                  {q.submitted_at ? new Date(q.submitted_at).toLocaleString() : "—"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>

        </div>

      </div>

    </div>
  );
}