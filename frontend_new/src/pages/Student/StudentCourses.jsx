import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import API from "../../api";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import "../../styles/Courses.css";

export default function StudentCourses() {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const [open, setOpen] = useState(false);
  const [courses, setCourses] = useState([]);
  const [loading, setLoading] = useState(true);

  // which semester's subjects to show ("" = not set yet)
  const [semFilter, setSemFilter] = useState("");

  useEffect(() => { fetchCourses(); }, []);

  const fetchCourses = async () => {
    try {
      setLoading(true);
      const res = await API.get("/enrollments/");
      const enrollments = res.data?.results || res.data || [];

      // this student's enrollments (all semesters — kept as history)
      const mine = enrollments.filter(
        (e) => (e.student?.id || e.student) === user.id
      );
      setCourses(mine);

      // default the filter to the student's current semester, if they have
      // subjects there; otherwise fall back to their latest semester with data
      const sems = [
        ...new Set(
          mine.map((e) => Number(e.semester)).filter((n) => !Number.isNaN(n))
        ),
      ].sort((a, b) => a - b);

      const current = Number(user.semester);
      if (sems.includes(current)) {
        setSemFilter(String(current));
      } else if (sems.length) {
        setSemFilter(String(sems[sems.length - 1])); // latest available
      } else {
        setSemFilter("");
      }
    } catch (err) {
      console.log("Error fetching courses:", err);
    } finally {
      setLoading(false);
    }
  };

  // semesters this student actually has subjects in (for the dropdown)
  const availableSemesters = [
    ...new Set(
      courses.map((c) => Number(c.semester)).filter((n) => !Number.isNaN(n))
    ),
  ].sort((a, b) => a - b);

  // rows to show = the selected semester (or all, if somehow unset)
  const visibleCourses = semFilter
    ? courses.filter((c) => Number(c.semester) === Number(semFilter))
    : courses;

  // the student's course id (all enrolled subjects share the same course)
  const courseId = courses[0]?.course_id;

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="courses-page">

              {/* ── Header ── */}
              <div className="courses-header">
                <div>
                  <h1 className="courses-title">My Subjects</h1>
                  <p className="courses-subtitle">View your enrolled subjects</p>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>

                  {/* Semester filter */}
                  {!loading && availableSemesters.length > 0 && (
                    <select
                      value={semFilter}
                      onChange={(e) => setSemFilter(e.target.value)}
                      style={{
                        padding: "8px 12px",
                        borderRadius: "10px",
                        border: "1px solid #E7E7EC",
                        background: "#F6F6F8",
                        fontSize: "15px",
                      }}
                    >
                      {availableSemesters.map((s) => (
                        <option key={s} value={s}>
                          Semester {s}
                          {Number(s) === Number(user.semester) ? " (current)" : ""}
                        </option>
                      ))}
                    </select>
                  )}

                  {!loading && courseId && (
                    <button
                      className="courses-open-btn"
                      onClick={() => navigate(`/courses/${courseId}/structure`)}
                    >
                      Course Structure
                    </button>
                  )}
                  {!loading && (
                    <span className="courses-count">
                      {visibleCourses.length} subject{visibleCourses.length !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              </div>

              {/* ── Loading ── */}
              {loading ? (
                <div className="courses-loading">
                  <div className="courses-spinner" />
                  <p>Loading subjects…</p>
                </div>

              ) : visibleCourses.length === 0 ? (
                <div className="courses-empty">
                  <p>No subjects found for this semester.</p>
                </div>

              ) : (
                <div className="courses-table-wrap">
                  <table className="courses-table">
                    <thead>
                      <tr>
                        <th>Course</th>
                        <th>Subject</th>
                        <th>Year</th>
                        <th>Teacher</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleCourses.map((c) => (
                        <tr key={c.id}>
                          <td>{c.course_name}</td>
                          <td className="courses-td-subject">{c.subject_name}</td>
                          <td>Year {c.year_number}</td>
                          <td>{c.teacher_name}</td>
                          <td>
                            <button
                              className="courses-open-btn"
                              onClick={() => navigate(`/student/subject/${c.teaching_assignment}`)}
                            >
                              Open
                            </button>
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