import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import API from "../../api";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import ImportExport from "../../components/ImportExport";
import "../../App.css";

export default function Courses() {
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [courses, setCourses] = useState([]);
  const [name, setName] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchCourses();
  }, []);

  const fetchCourses = async () => {
    try {
      setLoading(true);
      const res = await API.get("/courses/");
      setCourses(res.data?.results || res.data || []);
    } catch (err) {
      console.log("Error fetching courses:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!name.trim()) return alert("Enter a course name");

    try {
      setSaving(true);
      if (editingId) {
        await API.put(`/courses/${editingId}/`, { name });
      } else {
        await API.post("/courses/", { name });
      }
      setName("");
      setEditingId(null);
      fetchCourses();
    } catch (err) {
      console.log("Error saving course:", err);
      alert("Failed to save course");
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (course) => {
    setName(course.name);
    setEditingId(course.id);
  };

  const handleCancel = () => {
    setName("");
    setEditingId(null);
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this course?")) return;
    try {
      await API.delete(`/courses/${id}/`);
      setCourses((prev) => prev.filter((c) => c.id !== id));
    } catch (err) {
      console.log("Error deleting course:", err);
      alert("Failed to delete course");
    }
  };

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />

      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">
          <div className="content courses-page">

            {/* ================= HEADER ================= */}
            <div className="header-box" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
              <div>
                <h2>Course Management</h2>
                <p>Create and manage all courses</p>
              </div>
              <ImportExport
                align="right"
                onDone={fetchCourses}
                sets={[
                  { importer: "courses", title: "Courses", label: "courses", matchLabel: "course name" },
                  { importer: "subjects", title: "Subjects", label: "subjects",
                    matchLabel: "course, year, semester and subject name" },
                ]}
              />
            </div>

            {/* ================= ADD / EDIT ================= */}
            <div className="card">
              <div className="form-grid form-grid--row">
                <input
                  placeholder="Course name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                <button
                  className="btn-primary"
                  onClick={handleSubmit}
                  disabled={saving}
                >
                  {saving ? "Saving…" : editingId ? "Update" : "Add"}
                </button>
                {editingId && (
                  <button className="btn-delete" onClick={handleCancel}>
                    Cancel
                  </button>
                )}
              </div>
            </div>

            {/* ================= LIST ================= */}
            <div className="card">
              {loading ? (
                <p style={{ color: "#85839A" }}>Loading…</p>
              ) : courses.length === 0 ? (
                <p style={{ color: "#5D5A6B" }}>No courses yet.</p>
              ) : (
                <div className="table-container">
                  <table>
                    <thead>
                      <tr>
                        <th>Course name</th>
                        <th style={{ textAlign: "right" }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {courses.map((c) => (
                        <tr key={c.id}>
                          <td>{c.name}</td>
                          <td>
                            <div
                              className="action-buttons"
                              style={{ justifyContent: "flex-end" }}
                            >
                              <button
                                className="btn-edit"
                                onClick={() => navigate(`/courses/${c.id}`)}
                              >
                                View
                              </button>
                              <button
                                className="btn-edit"
                                onClick={() => handleEdit(c)}
                              >
                                Edit
                              </button>
                              <button
                                className="btn-delete"
                                onClick={() => handleDelete(c.id)}
                              >
                                Delete
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