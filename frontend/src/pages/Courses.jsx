import { useEffect, useState } from "react";
import Sidebar from "../components/Sidebar";
import Navbar from "../components/Navbar";
import API from "../api";

// =============================================================
//  Courses Page — Course Management (CRUD)
// =============================================================

export default function Courses() {

  // ─────────────────────────────────────────────────────────
  //  STATE
  // ─────────────────────────────────────────────────────────

  const [courses, setCourses]   = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [editingId, setEditingId] = useState(null);

  const [form, setForm] = useState({
    title:       "",
    description: "",
    teacher:     "",
  });


  // ─────────────────────────────────────────────────────────
  //  LIFECYCLE
  // ─────────────────────────────────────────────────────────

  useEffect(() => {
    fetchCourses();
    fetchTeachers();
  }, []);


  // ─────────────────────────────────────────────────────────
  //  API CALLS
  // ─────────────────────────────────────────────────────────

  const fetchCourses = async () => {
    try {
      const res = await API.get("courses/");
      setCourses(res.data || []);
    } catch (err) {
      console.error("Course fetch error:", err);
    }
  };

  const fetchTeachers = async () => {
    try {
      const res = await API.get("users/");
      const teacherList = (res.data || []).filter((u) => u.role === "teacher");
      setTeachers(teacherList);
    } catch (err) {
      console.error("Teacher fetch error:", err);
    }
  };


  // ─────────────────────────────────────────────────────────
  //  FORM HANDLERS
  // ─────────────────────────────────────────────────────────

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const payload = {
      ...form,
      teacher: Number(form.teacher), 
    };

    try {
      if (editingId) {
        await API.put(`courses/${editingId}/`, payload);
      } else {
        await API.post("courses/", payload);
      }

      // Reset form after success
      setForm({ title: "", description: "", teacher: "" });
      setEditingId(null);
      fetchCourses();
    } catch (err) {
      console.error("Submit error:", err);
    }
  };

  const handleEdit = (course) => {
    setForm({
      title:       course.title       || "",
      description: course.description || "",
      teacher:     course.teacher     || "",
    });
    setEditingId(course.id);
  };

  const handleDelete = async (id) => {
    try {
      await API.delete(`courses/${id}/`);
      fetchCourses();
    } catch (err) {
      console.error("Delete error:", err);
    }
  };


  // ─────────────────────────────────────────────────────────
  //  RENDER
  // ─────────────────────────────────────────────────────────

  return (
    <div className="layout">
      <Sidebar />

      <div className="main">
        <Navbar />

        <div className="content">

          {/* ── Page Header ───────────────────────────────── */}
          <div className="header-box">
            <h2>Course Management</h2>
          </div>

          {/* ── Add / Edit Form ───────────────────────────── */}
          <div className="card">
            <form onSubmit={handleSubmit} className="form-grid">

              <input
                type="text"
                name="title"
                placeholder="Course Title"
                value={form.title}
                onChange={handleChange}
                required
              />

              <input
                type="text"
                name="description"
                placeholder="Description"
                value={form.description}
                onChange={handleChange}
                required
              />

              <select
                name="teacher"
                value={form.teacher}
                onChange={handleChange}
                required
              >
                <option value="">Select Teacher</option>
                {teachers.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.username} ({t.department || "No Dept"})
                  </option>
                ))}
              </select>

              <button className="btn-primary" type="submit">
                {editingId ? "Update" : "Add"}
              </button>

            </form>
          </div>

          {/* ── Courses Table ─────────────────────────────── */}
          <div className="card">
            <table className="styled-table">
              <thead>
                <tr>
                  <th>Course</th>
                  <th>Description</th>
                  <th>Teacher</th>
                  <th>Department</th>
                  <th>Actions</th>
                </tr>
              </thead>

              <tbody>
                {courses.length === 0 ? (
                  <tr>
                    <td colSpan="5" style={{ textAlign: "center" }}>
                      No courses found
                    </td>
                  </tr>
                ) : (
                  courses.map((course) => (
                    <tr key={course.id}>
                      <td>{course.title}</td>
                      <td>{course.description}</td>
                      <td>{course.teacher_name}</td>
                      <td>{course.teacher_dept || "N/A"}</td>
                      <td>
                        <button
                          className="btn-edit"
                          onClick={() => handleEdit(course)}
                        >
                          Edit
                        </button>
                        <button
                          className="btn-danger"
                          onClick={() => handleDelete(course.id)}
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
  );
}