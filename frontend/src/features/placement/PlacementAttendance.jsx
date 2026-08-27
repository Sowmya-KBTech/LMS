import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

export default function PlacementAttendance() {

  const [open, setOpen] = useState(false);

  const [drives, setDrives] = useState([]);
  const [drive, setDrive] = useState(null);
  const [role, setRole] = useState(null);

  const [attendance, setAttendance] = useState(null);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // ================= INIT =================
  useEffect(() => {
    API.get("placement/drives/")
      .then((res) => setDrives(res.data || []))
      .catch((err) => {
        console.error("Drives error:", err.response?.data || err);
        setError("Could not load drives.");
      })
      .finally(() => setLoading(false));
  }, []);

  const selectDrive = (driveId) => {
    const d = drives.find((x) => x.id === Number(driveId)) || null;
    setDrive(d);
    setRole(null);
    setAttendance(null);
    setNotice("");
  };

  const selectRole = (roleId) => {
    const r = (drive?.job_roles || []).find((x) => x.id === Number(roleId)) || null;
    setRole(r);
    if (r) {
      loadAttendance(r.id);
    } else {
      setAttendance(null);
    }
  };

  // ================= ATTENDANCE =================
  const loadAttendance = (roleId) => {
    setBusy(true);
    setError("");

    API.get(`placement/roles/${roleId}/attendance/`)
      .then((res) => setAttendance(res.data))
      .catch((err) => {
        console.error("Attendance error:", err.response?.data || err);
        setError("Could not load the attendance sheet.");
      })
      .finally(() => setBusy(false));
  };

  const mark = async (applicationId, status) => {

    setError("");
    setNotice("");

    try {
      setBusy(true);

      const res = await API.post(
        `placement/roles/${role.id}/attendance/`,
        { application: applicationId, status }
      );

      // The note explains what happened to the student's classes -- an OD was
      // created and how many periods it covered, or why it could not be.
      // Worth surfacing, not swallowing.
      if (res.data?.note) {
        setNotice(res.data.note);
      }

      loadAttendance(role.id);

    } catch (err) {
      console.error("Mark error:", err.response?.data || err);
      setError(err.response?.data?.detail || "Could not mark attendance.");
      setBusy(false);
    }
  };

  const counts = attendance?.counts || {};

  return (
    <div className="app">

      <Navbar setOpen={setOpen} />

      <div className="layout">

        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">

          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">
              <h2>Drive attendance</h2>
              <p>
                Mark who turned up. Marking a student present approves their
                on-duty automatically.
              </p>
            </div>

            {/* ================= MESSAGES ================= */}
            {error && (
              <div
                className="card"
                style={{ borderLeft: "4px solid #dc2626", color: "#991b1b" }}
              >
                {error}
              </div>
            )}

            {notice && (
              <div
                className="card"
                style={{ borderLeft: "4px solid #16a34a", color: "#166534" }}
              >
                {notice}
              </div>
            )}

            {/* ================= PICKERS ================= */}
            <div className="card">

              <div className="form-grid form-grid--row">

                <select
                  value={drive?.id || ""}
                  onChange={(e) => selectDrive(e.target.value)}
                  disabled={loading}
                >
                  <option value="">
                    {loading ? "Loading drives..." : "Select a drive"}
                  </option>
                  {drives.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.company_name}
                      {d.title ? ` — ${d.title}` : ""}
                    </option>
                  ))}
                </select>

                <select
                  value={role?.id || ""}
                  onChange={(e) => selectRole(e.target.value)}
                  disabled={!drive}
                >
                  <option value="">
                    {!drive ? "Select a drive first" : "Select a role"}
                  </option>
                  {(drive?.job_roles || []).map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.title}
                    </option>
                  ))}
                </select>

                {role && (
                  <button
                    className="btn-edit"
                    onClick={() => loadAttendance(role.id)}
                    disabled={busy}
                  >
                    {busy ? "Refreshing..." : "Refresh"}
                  </button>
                )}

              </div>

              {drive && !drive.drive_date && (
                <p style={{ margin: "12px 0 0", fontSize: "13px", color: "#92400e" }}>
                  This drive has no date set, so marking a student present
                  cannot create an on-duty record. Set the date on the Drives
                  page first.
                </p>
              )}

            </div>

            {/* ================= SHEET ================= */}
            {role && (
              <div className="card">

                <h3>
                  {role.title}
                  {attendance ? ` (${counts.applied || 0} applied)` : ""}
                </h3>

                {attendance && (
                  <p style={{ margin: "0 0 12px", fontSize: "13px", color: "#64748b" }}>
                    Present {counts.present || 0} · Absent {counts.absent || 0} ·
                    Not marked {counts.unmarked || 0}
                    {attendance.drive_date
                      ? ` · Drive on ${attendance.drive_date}`
                      : ""}
                  </p>
                )}

                <table>
                  <thead>
                    <tr>
                      <th>Roll no</th>
                      <th>Student</th>
                      <th>Department</th>
                      <th>Status</th>
                      <th>OD</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {busy && !attendance ? (
                      <tr><td colSpan="6">Loading...</td></tr>
                    ) : attendance?.results?.length > 0 ? (
                      attendance.results.map((r) => (
                        <tr key={r.application}>
                          <td>{r.roll_number || "—"}</td>
                          <td>{r.student_name}</td>
                          <td>{r.department_name || "—"}</td>
                          <td>
                            {r.status === "present" && (
                              <span style={{ color: "#166534" }}>Present</span>
                            )}
                            {r.status === "absent" && (
                              <span style={{ color: "#991b1b" }}>Absent</span>
                            )}
                            {!r.status && (
                              <span style={{ color: "#64748b" }}>Not marked</span>
                            )}
                          </td>
                          <td>
                            {r.od_created ? (
                              <span style={{ color: "#166534" }}>Yes</span>
                            ) : (
                              <span style={{ color: "#64748b" }}>—</span>
                            )}
                          </td>
                          <td>
                            <div className="action-buttons">
                              <button
                                className={
                                  r.status === "present" ? "btn-primary" : "btn-edit"
                                }
                                onClick={() => mark(r.application, "present")}
                                disabled={busy}
                              >
                                Present
                              </button>
                              <button
                                className={
                                  r.status === "absent" ? "btn-delete" : "btn-edit"
                                }
                                onClick={() => mark(r.application, "absent")}
                                disabled={busy}
                              >
                                Absent
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan="6">
                          Nobody has applied for this role yet.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>

                {attendance?.results?.length > 0 && (
                  <p style={{ margin: "12px 0 0", fontSize: "13px", color: "#64748b" }}>
                    Only students who applied appear here. Marking present
                    approves an on-duty for the drive date and marks that day's
                    periods as duty leave — their attendance percentage is not
                    affected.
                  </p>
                )}

              </div>
            )}

            {/* ================= NOTHING PICKED ================= */}
            {!role && !loading && (
              <div className="card">
                <p style={{ margin: 0 }}>
                  {drives.length === 0
                    ? "No drives yet. Create one first."
                    : "Select a drive and a role to begin."}
                </p>
              </div>
            )}

          </div>

        </div>

      </div>

    </div>
  );
}