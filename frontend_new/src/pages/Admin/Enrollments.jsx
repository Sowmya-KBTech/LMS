import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

export default function Enrollments() {

  const [open, setOpen] = useState(false);

  const [enrollments, setEnrollments] = useState([]);

  // ✅ course filter
  const [courseFilter, setCourseFilter] = useState("all");

  const [generating, setGenerating] = useState(false);

  // ================= LOAD =================
  useEffect(() => {
    fetchEnrollments();
  }, []);

  // ================= FETCH ENROLLMENTS =================
  const fetchEnrollments = async () => {
    try {
      const res = await API.get("/enrollments/");
      setEnrollments(res.data?.results || res.data || []);
    } catch (err) {
      console.log(err);
    }
  };

  // ================= GENERATE ENROLLMENTS =================
  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const res = await API.post("/generate-enrollments/");

      // backend returns { message, created }
      const created = res.data?.created;
      if (created === 0) {
        alert("No new enrollments — all students are already enrolled.");
      } else {
        alert(`${created ?? "Some"} enrollments generated successfully`);
      }

      fetchEnrollments();
    } catch (err) {
      console.log(err.response?.data || err);
      const msg =
        err.response?.data?.error ||
        err.response?.data?.detail ||
        "Enrollment generation failed";
      alert(msg);
    } finally {
      setGenerating(false);
    }
  };

  // ================= DELETE =================
  const handleDelete = async (id) => {
    if (!window.confirm("Delete enrollment?")) {
      return;
    }
    try {
      await API.delete(`/enrollments/${id}/`);
      fetchEnrollments();
    } catch (err) {
      console.log(err);
    }
  };

  // ================= UNIQUE COURSES (for filter dropdown) =================
  const courseOptions = [
    ...new Map(
      enrollments
        .filter((e) => e.course_name)
        .map((e) => [e.course_name, e.course_name])
    ).keys(),
  ];

  // ================= FILTERED ENROLLMENTS =================
  const filteredEnrollments =
    courseFilter === "all"
      ? enrollments
      : enrollments.filter((e) => e.course_name === courseFilter);

  // ================= UI =================
  return (
    <div className="app">

      {/* NAVBAR */}
      <Navbar setOpen={setOpen} />

      <div className="layout">

        {/* SIDEBAR */}
        <Sidebar open={open} setOpen={setOpen} />

        {/* MAIN */}
        <div className="main">

          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">

              <h2>Enrollment Management</h2>

              <p>Generate and manage student enrollments</p>

              {/* GENERATE BUTTON */}
              <button
                className="btn-primary"
                onClick={handleGenerate}
                disabled={generating}
              >
                {generating ? "Generating..." : "Generate Enrollments"}
              </button>

            </div>

            {/* ================= TABLE ================= */}
            <div className="card">

              {/* FILTER BAR */}
              <div className="top-filters" style={{ alignItems: "center" }}>
                <label style={{ fontWeight: 600, fontSize: "15px" }}>
                  Filter by Course:
                </label>
                <select
                  value={courseFilter}
                  onChange={(e) => setCourseFilter(e.target.value)}
                  style={{ minWidth: "240px" }}
                >
                  <option value="all">All Courses</option>
                  {courseOptions.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
                <span
                  style={{
                    marginLeft: "auto",
                    fontSize: "14px",
                    color: "#5D5A6B",
                  }}
                >
                  Showing {filteredEnrollments.length} of {enrollments.length}
                </span>
              </div>

              <table>

                <thead>
                  <tr>
                    <th>Student</th>
                    <th>Course</th>
                    <th>Year</th>
                    <th>Semester</th>
                    <th>Subject</th>
                    <th>Teacher</th>
                    <th>Action</th>
                  </tr>
                </thead>

                <tbody>

                  {filteredEnrollments.length === 0 ? (
                    <tr>
                      <td colSpan="7">No enrollments</td>
                    </tr>
                  ) : (
                    filteredEnrollments.map((e) => (
                      <tr key={e.id}>
                        <td>{e.student_name}</td>
                        <td>{e.course_name}</td>
                        <td>Year {e.year_number}</td>
                        <td>Semester {e.semester}</td>
                        <td>{e.subject_name}</td>
                        <td>{e.teacher_name}</td>
                        <td>
                          <button
                            className="btn-delete"
                            onClick={() => handleDelete(e.id)}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))
                  )}

                </tbody>

              </table>

            </div>

          </div>

        </div>

      </div>

    </div>
  );
}