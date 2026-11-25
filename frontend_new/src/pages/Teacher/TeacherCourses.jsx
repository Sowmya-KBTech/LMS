import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import API from "../../api";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import "../../App.css";

export default function TeacherCourses() {
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [assignments, setAssignments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [semester, setSemester] = useState("all");

  useEffect(() => {
    fetchAssignments();
  }, []);

  const fetchAssignments = async () => {
    try {
      setLoading(true);
      // ?my=true is REQUIRED — without it the endpoint returns every
      // teaching assignment in the college, not just this teacher's.
      const res = await API.get("/teaching-assignments/?my=true");
      setAssignments(res.data?.results || res.data || []);
    } catch (err) {
      console.log("Error fetching my subjects:", err);
    } finally {
      setLoading(false);
    }
  };

  // distinct semesters this teacher actually teaches, ascending
  const semesters = useMemo(() => {
    const s = [...new Set(assignments.map((a) => a.semester).filter(Boolean))];
    return s.sort((a, b) => a - b);
  }, [assignments]);

  const filtered = useMemo(() => {
    if (semester === "all") return assignments;
    return assignments.filter((a) => String(a.semester) === String(semester));
  }, [assignments, semester]);

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />

      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">
          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">
              <h2>My Subjects</h2>
              <p>The subjects you are assigned to teach</p>
            </div>

            {/* ================= FILTER ================= */}
            {semesters.length > 1 && (
              <div className="top-filters" style={{ marginBottom: 0 }}>
                <select
                  value={semester}
                  onChange={(e) => setSemester(e.target.value)}
                  style={{ minWidth: 180 }}
                >
                  <option value="all">All semesters</option>
                  {semesters.map((s) => (
                    <option key={s} value={s}>Semester {s}</option>
                  ))}
                </select>
              </div>
            )}

            {/* ================= LIST ================= */}
            <div className="card">
              {loading ? (
                <p style={{ color: "#85839A" }}>Loading…</p>
              ) : filtered.length === 0 ? (
                <p style={{ color: "#5D5A6B" }}>
                  {assignments.length === 0
                    ? "No subjects assigned to you yet. Your HOD allocates subjects to faculty."
                    : "No subjects in this semester."}
                </p>
              ) : (
                <div className="table-container">
                  <table>
                    <thead>
                      <tr>
                        <th>Subject</th>
                        <th>Course</th>
                        <th>Year</th>
                        <th>Semester</th>
                        <th style={{ textAlign: "right" }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((a) => (
                        <tr key={a.id}>
                          <td style={{ fontWeight: 500 }}>{a.subject_name || "—"}</td>
                          <td>{a.course_name || "—"}</td>
                          <td>{a.year_number ? `Year ${a.year_number}` : "—"}</td>
                          <td>{a.semester ? `Semester ${a.semester}` : "—"}</td>
                          <td>
                            <div
                              className="action-buttons"
                              style={{ justifyContent: "flex-end" }}
                            >
                              <button
                                className="btn-edit"
                                onClick={() => navigate(`/teacher/subject/${a.id}`)}
                              >
                                Open
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}