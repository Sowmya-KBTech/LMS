import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";
import ImportExport from "../../components/ImportExport";

import "../../App.css";

export default function Departments() {

  // ================= STATES =================
  const [open, setOpen] = useState(false);
  const [departments, setDepartments] = useState([]);
  const [teachers, setTeachers] = useState([]);
  const [name, setName] = useState("");
  const [editing, setEditing] = useState(null);

  // ================= LOAD =================
  useEffect(() => {
    fetchDepartments();
    fetchTeachers();
  }, []);

  // ================= MESSAGE =================
  const showToast = (msg) => {
    alert(msg);
  };

  // ================= FETCH DEPARTMENTS =================
  const fetchDepartments = async () => {
    try {
      const res = await API.get("users/departments/");
      const data = res.data?.results || res.data;
      setDepartments(Array.isArray(data) ? data : []);
    } catch {
      showToast("Failed to load departments");
    }
  };

  // ================= FETCH TEACHERS =================
  const fetchTeachers = async () => {
    try {
      const res = await API.get("users/?role=teacher");
      const data = res.data?.results || res.data;
      setTeachers(Array.isArray(data) ? data : []);
    } catch {
      showToast("Failed to load teachers");
    }
  };

  // ================= ADD =================
  const handleAdd = async () => {
    if (!name.trim()) {
      return showToast("Enter department name");
    }
    try {
      await API.post("users/departments/", { name });
      setName("");
      fetchDepartments();
      showToast("Department added");
    } catch (err) {
      showToast(JSON.stringify(err.response?.data));
    }
  };

  // ================= EDIT =================
  const handleEdit = (d) => {
    setEditing(d);
    setName(d.name);
  };

  // ================= UPDATE =================
  const handleUpdate = async () => {
    if (!name.trim()) {
      return showToast("Enter department name");
    }
    try {
      await API.patch(`users/departments/${editing.id}/`, { name });
      setEditing(null);
      setName("");
      fetchDepartments();
      showToast("Department updated");
    } catch (err) {
      showToast(JSON.stringify(err.response?.data));
    }
  };

  // ================= ASSIGN HOD =================
  const handleAssignHOD = async (deptId, teacherId) => {
    try {
      await API.patch(`users/departments/${deptId}/`, {
        hod: teacherId || null,
      });
      fetchDepartments();
      showToast(teacherId ? "HOD assigned" : "HOD removed");
    } catch (err) {
      showToast(JSON.stringify(err.response?.data));
    }
  };

  // ================= DELETE =================
  const handleDelete = async (id) => {
    if (!window.confirm("Delete department?")) return;
    try {
      await API.delete(`users/departments/${id}/`);
      fetchDepartments();
      showToast("Department deleted");
    } catch {
      showToast("Delete failed");
    }
  };

  // ================= CANCEL =================
  const handleCancel = () => {
    setEditing(null);
    setName("");
  };

  // teachers belonging to a given department (matches by id OR name)
  const deptTeachers = (dept) =>
    teachers.filter((t) => {
      const byId = Number(t.department) === Number(dept.id);
      const byName =
        t.department_name &&
        dept.name &&
        t.department_name.toLowerCase() === dept.name.toLowerCase();
      return byId || byName;
    });

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">
          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
              <div>
                <h2>Departments</h2>
                <p>Manage college departments</p>
              </div>
              {/* IMPORT / EXPORT: name, code and HOD for every department */}
              <ImportExport
                align="right"
                importer="departments"
                label="departments"
                matchLabel="department name"
                note="Add departments first and leave HOD empty; after staff are imported, fill the HOD column (Employee ID) and import again."
                onDone={fetchDepartments}
              />
            </div>

            {/* ================= FORM CARD ================= */}
            <div className="card">
              <h3>{editing ? "Edit Department" : "Add Department"}</h3>
              <div className="form-grid">
                <input
                  type="text"
                  placeholder="Department Name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                <button
                  className="btn-primary"
                  style={{
                    padding: "6px 14px",
                    fontSize: "14px",
                    width: "150px",
                    height: "38px",
                    borderRadius: "6px",
                    flex: "none",
                  }}
                  onClick={editing ? handleUpdate : handleAdd}
                >
                  {editing ? "Update" : "Add"}
                </button>
                {editing && (
                  <button className="btn-delete" onClick={handleCancel}>
                    Cancel
                  </button>
                )}
              </div>
            </div>

            {/* ================= TABLE CARD ================= */}
            <div className="card">
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Department</th>
                      <th>Head of Department (HOD)</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {departments.length > 0 ? (
                      departments.map((d) => {
                        const myTeachers = deptTeachers(d);
                        return (
                          <tr key={d.id}>
                            <td>{d.name}</td>

                            {/* HOD column */}
                            <td>
                              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                                <select
                                  value={d.hod || ""}
                                  onChange={(e) => handleAssignHOD(d.id, e.target.value)}
                                  style={{ minWidth: 180 }}
                                >
                                  <option value="">— No HOD —</option>
                                  {myTeachers.length === 0 ? (
                                    <option value="" disabled>
                                      No teachers in this dept
                                    </option>
                                  ) : (
                                    myTeachers.map((t) => (
                                      <option key={t.id} value={t.id}>
                                        {t.username}
                                      </option>
                                    ))
                                  )}
                                </select>

                                {d.hod_name && (
                                  <span
                                    style={{
                                      display: "inline-flex",
                                      alignItems: "center",
                                      gap: 6,
                                      background: "#ecfdf3",
                                      color: "#15803d",
                                      border: "1px solid #bbf7d0",
                                      padding: "5px 12px",
                                      borderRadius: 999,
                                      fontSize: 14,
                                      fontWeight: 600,
                                      whiteSpace: "nowrap",
                                    }}
                                  >
                                    ● {d.hod_name}
                                  </span>
                                )}
                              </div>
                            </td>

                            <td>
                              <div className="action-buttons">
                                <button className="btn-edit" onClick={() => handleEdit(d)}>
                                  Edit
                                </button>
                                <button className="btn-delete" onClick={() => handleDelete(d.id)}>
                                  Delete
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td colSpan="3">No departments found</td>
                      </tr>
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