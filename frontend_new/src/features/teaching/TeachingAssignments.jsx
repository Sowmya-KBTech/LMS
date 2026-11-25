import { useEffect, useState } from "react";
import Select from "react-select";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";
import ImportExport from "../../components/ImportExport";

import "../../App.css";

export default function TeachingAssignments() {

  const [open, setOpen] = useState(false);

  const [courses, setCourses] = useState([]);
  const [years, setYears] = useState([]);
  const [subjects, setSubjects] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [assignments, setAssignments] = useState([]);

  const [form, setForm] = useState({
    course: "",
    year: "",
    subject: "",
    teacher: "",
  });

  const [editId, setEditId] = useState(null);

  // ✅ course filter for the table
  const [courseFilter, setCourseFilter] = useState("all");

  // ✅ enrollment generation state (moved here from the old Enrollments page)
  const [generating, setGenerating] = useState(false);

  // ================= LOAD =================
  useEffect(() => {
    fetchData();
  }, []);

  // ================= FETCH =================
  const fetchData = async () => {
    try {
      const [c, y, s, u, a] = await Promise.all([
        API.get("/courses/"),
        API.get("/years/"),
        API.get("/subjects/"),
        API.get("/users/"),
        API.get("/teaching-assignments/"),
      ]);

      // ================= FILTER TEACHERS =================
      const teachersOnly = (u.data?.results || u.data || []).filter(
        (user) => user.role === "teacher"
      );

      setCourses(c.data?.results || c.data || []);
      setYears(y.data?.results || y.data || []);
      setSubjects(s.data?.results || s.data || []);
      setTeachers(teachersOnly);
      setAssignments(a.data?.results || a.data || []);
    } catch (err) {
      console.error("Fetch error:", err.response?.data || err);
    }
  };

  // ================= GENERATE ENROLLMENTS =================
  // Same call the old Enrollments page used. After allocating teachers to
  // subjects, this creates the per-student enrollment rows (skipping students
  // who are already enrolled). Kept as a page-level bulk action.
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

  // ================= FILTER YEARS =================
  const filteredYears = years.filter(
    (y) => Number(y.course) === Number(form.course)
  );

  // ================= FILTER SUBJECTS =================
  const filteredSubjects = subjects.filter((s) => {
    // Subject must belong to selected year
    if (Number(s.year) !== Number(form.year)) {
      return false;
    }

    // During edit mode, show current subject
    if (editId && Number(s.id) === Number(form.subject)) {
      return true;
    }

    // Hide already assigned subjects
    const alreadyAssigned = assignments.some(
      (a) =>
        Number(a.course) === Number(form.course) &&
        Number(a.year) === Number(form.year) &&
        Number(a.subject) === Number(s.id) &&
        Number(a.id) !== Number(editId)
    );

    return !alreadyAssigned;
  });

  // ================= FILTER ASSIGNMENTS BY COURSE =================
  const filteredAssignments =
    courseFilter === "all"
      ? assignments
      : assignments.filter(
          (a) => String(a.course) === String(courseFilter)
        );

  // ================= EDIT =================
  const handleEdit = (a) => {
    setForm({
      course: a.course,
      year: a.year,
      subject: a.subject,
      teacher: a.teacher,
    });
    setEditId(a.id);
  };

  // ================= CREATE / UPDATE =================
  const handleAssign = async () => {
    if (!form.course || !form.year || !form.subject || !form.teacher) {
      alert("Please fill all fields");
      return;
    }

    try {
      // ================= UPDATE =================
      if (editId) {
        await API.put(`/teaching-assignments/${editId}/`, form);
        alert("Updated successfully");
      } else {
        // ================= CHECK DUPLICATE =================
        const exists = assignments.find(
          (a) =>
            Number(a.course) === Number(form.course) &&
            Number(a.year) === Number(form.year) &&
            Number(a.subject) === Number(form.subject) &&
            Number(a.teacher) === Number(form.teacher)
        );

        if (exists) {
          alert("This assignment already exists");
          return;
        }

        // ================= CREATE =================
        await API.post("/teaching-assignments/", form);
        alert("Assigned successfully");
      }

      // ================= RESET =================
      setForm({
        course: "",
        year: "",
        subject: "",
        teacher: "",
      });

      setEditId(null);
      fetchData();
    } catch (err) {
      console.error(err.response?.data || err);
      alert("Operation failed");
    }
  };

  // ================= DELETE =================
  const handleDelete = async (id) => {
    if (!window.confirm("Delete this assignment?")) {
      return;
    }

    try {
      await API.delete(`/teaching-assignments/${id}/`);
      fetchData();
    } catch (err) {
      alert("Delete failed");
    }
  };

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
            <div
              className="header-box"
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: 12,
              }}
            >
              <div>
                <h2>Faculty Allocation</h2>
                <p>Assign teachers to subjects and semesters</p>
              </div>

              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                {/* bulk add from Excel (meeting point 2) - existing rows are skipped */}
                <ImportExport
                  importer="teaching_assignments"
                  label="teaching assignments"
                  matchLabel="teacher, course, year and subject"
                  modes={["upsert"]}
                  align="right"
                  exportParams={{ course: courseFilter === "all" ? "" : courseFilter }}
                  note="One row per teacher + subject. Teacher = Employee ID, username or email. Rows that already exist are skipped. Click Generate Enrollments after importing."
                  onDone={fetchData}
                />

                {/* GENERATE ENROLLMENTS (moved from the old Enrollments page) */}
                <button
                  className="btn-primary"
                  onClick={handleGenerate}
                  disabled={generating}
                >
                  {generating ? "Generating..." : "Generate Enrollments"}
                </button>
              </div>
            </div>

            {/* ================= FORM ================= */}
            <div className="card">

              <div className="form-grid">

                {/* COURSE */}
                <select
                  value={form.course}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      course: Number(e.target.value),
                      year: "",
                      subject: "",
                    })
                  }
                >
                  <option value="">Select Course</option>
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>

                {/* YEAR */}
                <select
                  value={form.year}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      year: Number(e.target.value),
                      subject: "",
                    })
                  }
                >
                  <option value="">Select Year</option>
                  {filteredYears.map((y) => (
                    <option key={y.id} value={y.id}>
                      Year {y.year_number}
                    </option>
                  ))}
                </select>

                {/* SUBJECT */}
                <select
                  value={form.subject}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      subject: Number(e.target.value),
                    })
                  }
                >
                  <option value="">Select Subject</option>
                  {filteredSubjects.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} (Semester {s.semester})
                    </option>
                  ))}
                </select>

                {/* TEACHER */}
                <Select
                  className="teacher-select"
                  classNamePrefix="teacher-select"
                  placeholder="Select Teacher"
                  isSearchable
                  options={teachers.map((t) => ({
                    value: t.id,
                    label: `${t.username} (${t.department_name})`,
                  }))}
                  value={
                    teachers
                      .filter((t) => t.id === form.teacher)
                      .map((t) => ({
                        value: t.id,
                        label: `${t.username} (${t.department_name})`,
                      }))[0] || null
                  }
                  onChange={(selected) =>
                    setForm({
                      ...form,
                      teacher: selected ? selected.value : "",
                    })
                  }
                />

                {/* BUTTON */}
                <button className="btn-primary" onClick={handleAssign}>
                  {editId ? "Update" : "Assign"}
                </button>

                {/* CANCEL */}
                {editId && (
                  <button
                    className="btn-delete"
                    onClick={() => {
                      setEditId(null);
                      setForm({
                        course: "",
                        year: "",
                        subject: "",
                        teacher: "",
                      });
                    }}
                  >
                    Cancel
                  </button>
                )}

              </div>

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
                  {courses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
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
                  Showing {filteredAssignments.length} of {assignments.length}
                </span>
              </div>

              <div className="table-container">

                <table>

                  <thead>
                    <tr>
                      <th>Course</th>
                      <th>Year</th>
                      <th>Semester</th>
                      <th>Subject</th>
                      <th>Teacher</th>
                      <th>Action</th>
                    </tr>
                  </thead>

                  <tbody>

                    {filteredAssignments.length === 0 ? (
                      <tr>
                        <td colSpan="6">No assignments found</td>
                      </tr>
                    ) : (
                      filteredAssignments.map((a) => (
                        <tr key={a.id}>
                          <td>{a.course_name}</td>
                          <td>Year {a.year_number}</td>
                          <td>Semester {a.semester}</td>
                          <td>{a.subject_name}</td>
                          <td>{a.teacher_name}</td>
                          <td>
                            
                            <div className="action-buttons">
                              {/* EDIT */}
                              <button
                                className="btn-edit"
                                onClick={() => handleEdit(a)}
                              >
                                Edit
                              </button>

                              {/* DELETE */}
                              <button
                                className="btn-delete"
                                onClick={() => handleDelete(a.id)}
                              >
                                Delete
                              </button>
                            </div>
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

    </div>
  );
}