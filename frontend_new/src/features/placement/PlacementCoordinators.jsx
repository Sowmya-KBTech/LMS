import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

export default function PlacementCoordinators() {

  const [open, setOpen] = useState(false);

  const [coordinators, setCoordinators] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [teachers, setTeachers] = useState([]);

  const [teacher, setTeacher] = useState("");
  const [department, setDepartment] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // ================= INIT =================
  useEffect(() => {
    loadAll();
  }, []);

  // Each request updates its own piece of state instead of everything waiting
  // on the slowest one (this used to be a single Promise.all). The dropdowns
  // fill as their data lands, and the table is not held back by a request it
  // does not need.
  const loadAll = () => {
    setLoading(true);

    API.get("placement/coordinators/")
      .then((res) => setCoordinators(res.data || []))
      .catch((err) => {
        console.error("Coordinators load error:", err.response?.data || err);
        setError("Could not load coordinators.");
      })
      .finally(() => setLoading(false));

    API.get("placement/departments/")
      .then((res) => setDepartments(res.data || []))
      .catch((err) =>
        console.error("Departments load error:", err.response?.data || err)
      );

    API.get("placement/assignable-teachers/")
      .then((res) => setTeachers(res.data || []))
      .catch((err) =>
        console.error("Teachers load error:", err.response?.data || err)
      );
  };

  // ================= ASSIGN =================
  const handleAssign = async () => {

    setError("");

    if (!teacher || !department) {
      return alert("Select a teacher and a department");
    }

    try {
      setSaving(true);

      const res = await API.post("placement/coordinators/", {
        teacher: Number(teacher),
        department: Number(department),
        is_active: true,
      });

      // instant: prepend the new row rather than refetching the whole list
      setCoordinators((prev) => [res.data, ...prev]);

      setTeacher("");
      setDepartment("");

    } catch (err) {
      const data = err.response?.data;
      console.error("Assign error:", data);

      // the backend returns a readable message when a department already has
      // an active coordinator -- show it instead of a generic failure
      const message =
        data?.department?.[0] ||
        data?.teacher?.[0] ||
        data?.detail ||
        "Failed to assign coordinator.";

      setError(message);

    } finally {
      setSaving(false);
    }
  };

  // ================= DEACTIVATE =================
  const handleDeactivate = async (id, name) => {

    if (!window.confirm(`End ${name}'s coordinator assignment?`)) {
      return;
    }

    setError("");

    try {
      setSaving(true);

      await API.delete(`placement/coordinators/${id}/`);

      // The row is NOT removed -- the backend deactivates it so the history
      // stays. Reflect that here rather than dropping it from the list.
      setCoordinators((prev) =>
        prev.map((c) =>
          c.id === id ? { ...c, is_active: false } : c
        )
      );

    } catch (err) {
      console.error("Deactivate error:", err.response?.data || err);
      setError("Failed to deactivate.");
    } finally {
      setSaving(false);
    }
  };

  // ================= REACTIVATE =================
  const handleReactivate = async (id) => {

    setError("");

    try {
      setSaving(true);

      const res = await API.patch(`placement/coordinators/${id}/`, {
        is_active: true,
      });

      setCoordinators((prev) =>
        prev.map((c) => (c.id === id ? res.data : c))
      );

    } catch (err) {
      const data = err.response?.data;
      console.error("Reactivate error:", data);
      setError(
        data?.department?.[0] || data?.detail || "Failed to reactivate."
      );
    } finally {
      setSaving(false);
    }
  };

  const active = coordinators.filter((c) => c.is_active);
  const past = coordinators.filter((c) => !c.is_active);

  // a department that already has an active coordinator cannot take another
  const takenDepartmentIds = new Set(active.map((c) => c.department));

  return (
    <div className="app">

      <Navbar setOpen={setOpen} />

      <div className="layout">

        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">

          <div className="content">

            {/* ================= HEADER ================= */}
            {/* Rendered immediately. This page used to return a bare
                "Loading..." in place of the entire layout, so the sidebar,
                navbar and header were all withheld until three requests
                finished -- a blank screen, then everything at once. */}
            <div className="header-box">
              <h2>Placement Coordinators</h2>
              <p>
                One active coordinator per department. Coordinators keep all
                their teaching duties.
              </p>
            </div>

            {/* ================= ERROR ================= */}
            {error && (
              <div
                className="card"
                style={{
                  borderLeft: "4px solid #dc2626",
                  color: "#991b1b",
                }}
              >
                {error}
              </div>
            )}

            {/* ================= ASSIGN ================= */}
            <div className="card">

              <h3>Assign Coordinator</h3>

              <div className="form-grid form-grid--row">

                <select
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  disabled={departments.length === 0}
                >
                  <option value="">
                    {departments.length === 0
                      ? "Loading departments..."
                      : "Select Department"}
                  </option>
                  {departments.map((d) => (
                    <option
                      key={d.id}
                      value={d.id}
                      disabled={takenDepartmentIds.has(d.id)}
                    >
                      {d.name}
                      {takenDepartmentIds.has(d.id) ? " (has coordinator)" : ""}
                    </option>
                  ))}
                </select>

                <select
                  value={teacher}
                  onChange={(e) => setTeacher(e.target.value)}
                  disabled={teachers.length === 0}
                >
                  <option value="">
                    {teachers.length === 0
                      ? "Loading teachers..."
                      : "Select Teacher"}
                  </option>
                  {teachers.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.username}
                      {t.department_name ? ` — ${t.department_name}` : ""}
                    </option>
                  ))}
                </select>

                <button
                  className="btn-primary"
                  onClick={handleAssign}
                  disabled={saving}
                >
                  {saving ? "Saving..." : "Assign"}
                </button>

              </div>

            </div>

            {/* ================= ACTIVE ================= */}
            <div className="card">

              <h3>Active {loading ? "" : `(${active.length})`}</h3>

              <table>
                <thead>
                  <tr>
                    <th>Department</th>
                    <th>Code</th>
                    <th>Teacher</th>
                    <th>Employee ID</th>
                    <th>Assigned</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan="6">Loading...</td>
                    </tr>
                  ) : active.length > 0 ? (
                    active.map((c) => (
                      <tr key={c.id}>
                        <td>{c.department_name}</td>
                        <td>{c.department_code || "-"}</td>
                        <td>{c.teacher_name}</td>
                        <td>{c.teacher_employee_id || "-"}</td>
                        <td>
                          {c.assigned_at
                            ? new Date(c.assigned_at).toLocaleDateString()
                            : "-"}
                        </td>
                        <td>
                          <div className="action-buttons">
                            <button
                              className="btn-delete"
                              onClick={() =>
                                handleDeactivate(c.id, c.teacher_name)
                              }
                              disabled={saving}
                            >
                              End
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="6">No coordinators assigned yet</td>
                    </tr>
                  )}
                </tbody>
              </table>

            </div>

            {/* ================= PAST ================= */}
            {!loading && past.length > 0 && (
              <div className="card">

                <h3>Past ({past.length})</h3>

                <table>
                  <thead>
                    <tr>
                      <th>Department</th>
                      <th>Teacher</th>
                      <th>Assigned</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {past.map((c) => (
                      <tr key={c.id}>
                        <td>{c.department_name}</td>
                        <td>{c.teacher_name}</td>
                        <td>
                          {c.assigned_at
                            ? new Date(c.assigned_at).toLocaleDateString()
                            : "-"}
                        </td>
                        <td>
                          <div className="action-buttons">
                            <button
                              className="btn-edit"
                              onClick={() => handleReactivate(c.id)}
                              disabled={saving}
                            >
                              Reactivate
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
  );
}