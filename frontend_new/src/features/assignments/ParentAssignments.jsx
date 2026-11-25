import { useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import API from "../../api";
import "../../styles/ParentModule.css";

export default function ParentAssignments() {
  const [open, setOpen] = useState(false);
  const [children, setChildren] = useState([]);
  const [activeChild, setActiveChild] = useState(null);
  const [assignments, setAssignments] = useState([]);
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    API.get("/parent/dashboard/")
      .then((res) => setChildren(res.data?.children || []))
      .catch((err) => console.log("children fetch error:", err));
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const q = activeChild ? `?child=${activeChild}` : "";
      const aRes = await API.get(`/assignments/${q}`);
      setAssignments(aRes.data?.results || aRes.data || []);
      const sRes = await API.get(`/submissions/${q}`);
      setSubmissions(sRes.data?.results || sRes.data || []);
    } catch (err) {
      console.log("Parent assignments fetch error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const t = setInterval(fetchData, 15000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChild]);

  const today = new Date().setHours(0, 0, 0, 0);

  // Build a row per (assignment × child) joined with that child's submission.
  const rows = [];
  const childList = activeChild
    ? children.filter((c) => c.id === activeChild)
    : children;

  assignments.forEach((a) => {
    childList.forEach((c) => {
      const sub = submissions.find(
        (s) =>
          (s.assignment === a.id || s.assignment?.id === a.id) &&
          ((s.student?.id || s.student) === c.id || s.student_name === c.username)
      );
      let status = "Pending";
      if (sub) {
        status = sub.status
          ? sub.status.charAt(0).toUpperCase() + sub.status.slice(1)
          : "Submitted";
      } else if (a.due_date && new Date(a.due_date).setHours(0, 0, 0, 0) < today) {
        status = "Overdue";
      }
      rows.push({
        key: `${a.id}-${c.id}`,
        child: c.username,
        subject: a.subject_name || sub?.subject_name || "—",
        title: a.title,
        due: a.due_date,
        submittedOn: sub?.submitted_at,
        score:
          sub && sub.marks !== null && sub.marks !== undefined
            ? `${sub.marks}/${sub.total_marks}`
            : "—",
        status,
      });
    });
  });

  const badge = (status) => {
    const s = status.toLowerCase();
    if (s === "graded") return "pm-badge green";
    if (s === "submitted") return "pm-badge blue";
    if (s === "pending") return "pm-badge yellow";
    if (s === "overdue") return "pm-badge red";
    return "pm-badge gray";
  };

  const fmtDate = (iso) =>
    iso ? new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—";

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="pm-page">

              <div className="pm-header">
                <h1>Assignments</h1>
                <p>Track submission status for your children</p>
              </div>

              <div className="pm-tabs">
                <div
                  className={`pm-tab ${activeChild === null ? "active" : ""}`}
                  onClick={() => setActiveChild(null)}
                >
                  All Children
                </div>
                {children.map((c) => (
                  <div
                    key={c.id}
                    className={`pm-tab ${activeChild === c.id ? "active" : ""}`}
                    onClick={() => setActiveChild(c.id)}
                  >
                    {c.username}
                  </div>
                ))}
              </div>

              {loading ? (
                <div className="pm-loading">Loading assignments…</div>
              ) : (
                <div className="pm-card">
                  {rows.length === 0 ? (
                    <div className="pm-empty">No assignments found</div>
                  ) : (
                    <table className="pm-table">
                      <thead>
                        <tr>
                          <th>Child</th><th>Subject</th><th>Title</th>
                          <th>Due date</th><th>Submitted on</th><th>Score</th><th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((r) => (
                          <tr key={r.key}>
                            <td>{r.child}</td>
                            <td>{r.subject}</td>
                            <td>{r.title}</td>
                            <td>{fmtDate(r.due)}</td>
                            <td>{fmtDate(r.submittedOn)}</td>
                            <td>{r.score}</td>
                            <td><span className={badge(r.status)}>{r.status}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}