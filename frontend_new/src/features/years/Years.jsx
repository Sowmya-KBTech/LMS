import { useEffect, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../App.css";

export default function Years() {
  const [courses, setCourses] = useState([]);
  const [years, setYears] = useState([]);
  const [open, setOpen] = useState(false);

  const [form, setForm] = useState({
    course: "",
    year_number: "",
  });

  useEffect(() => {
    fetchData();
  }, []);

  // ================= FETCH =================
  const fetchData = async () => {
    try {
      const [c, y] = await Promise.all([
        API.get("/courses/"),
        API.get("/years/"),
      ]);

      setCourses(c.data?.results || c.data || []);
      setYears(y.data?.results || y.data || []);
    } catch (err) {
      console.log("Error:", err);
    }
  };

  // ================= ADD YEAR =================
  const handleAdd = async () => {
    if (!form.course || !form.year_number) {
      alert("Fill all fields");
      return;
    }

    const exists = years.find(
      (y) =>
        String(y.course) === String(form.course) &&
        String(y.year_number) === String(form.year_number)
    );

    if (exists) {
      alert("Year already exists for this course");
      return;
    }

    try {
      await API.post("/years/", form);
      setForm({ course: "", year_number: "" });
      fetchData();
    } catch (err) {
      alert("Failed to add year");
    }
  };

  // ================= DELETE =================
  const handleDelete = async (id) => {
    if (!window.confirm("Delete this year?")) return;

    try {
      await API.delete(`/years/${id}/`);
      fetchData();
    } catch (err) {
      alert("Delete failed");
    }
  };

  return (
    <div className="app">

      {/* FULL WIDTH NAVBAR */}
      <Navbar setOpen={setOpen} />

      <div className="layout">

        {/* SIDEBAR */}
        <Sidebar open={open} setOpen={setOpen} />

        {/* MAIN */}
        <div className="main">
          <div className="content">

            {/* HEADER */}
            <div className="header-box">
              <h2>Years Management</h2>
              <p>Manage course years</p>
            </div>

            {/* ===== ADD FORM ===== */}
            <div className="card">
              <h3>Add Year</h3>

              <div className="form-grid">

                {/* COURSE */}
                <select
                  value={form.course}
                  onChange={(e) =>
                    setForm({ ...form, course: e.target.value })
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
                  value={form.year_number}
                  onChange={(e) =>
                    setForm({ ...form, year_number: e.target.value })
                  }
                >
                  <option value="">Select Year</option>
                  <option value="1">Year 1</option>
                  <option value="2">Year 2</option>
                  <option value="3">Year 3</option>
                  <option value="4">Year 4</option>
                </select>

                {/* BUTTON */}
                <button className="btn-primary" onClick={handleAdd}>
                  Add Year
                </button>

              </div>
            </div>

            {/* ===== TABLE ===== */}
            <div className="card">
              <div className="table-container">

                <table>
                  <thead>
                    <tr>
                      <th>Course</th>
                      <th>Year</th>
                      <th>Action</th>
                    </tr>
                  </thead>

                  <tbody>
                    {years.map((y) => (
                      <tr key={y.id}>
                        <td>{y.course_name}</td>
                        <td>Year {y.year_number}</td>
                        <td>
                          <button
                            className="btn-delete"
                            onClick={() => handleDelete(y.id)}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {years.length === 0 && (
                  <p style={{ marginTop: "10px" }}>
                    No years added yet
                  </p>
                )}

              </div>
            </div>

          </div>
        </div>

      </div>
    </div>
  );
}