import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

export default function PlacementApplications() {

  const [open, setOpen] = useState(false);

  const [drives, setDrives] = useState([]);
  const [selectedDrive, setSelectedDrive] = useState(null);
  const [selectedRole, setSelectedRole] = useState(null);

  const [data, setData] = useState(null);
  const [tab, setTab] = useState("applied");

  const [loading, setLoading] = useState(true);
  const [rowsLoading, setRowsLoading] = useState(false);
  const [error, setError] = useState("");

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
    const drive = drives.find((d) => d.id === Number(driveId)) || null;
    setSelectedDrive(drive);
    setSelectedRole(null);
    setData(null);
  };

  const selectRole = (roleId) => {
    const role =
      (selectedDrive?.job_roles || []).find((r) => r.id === Number(roleId)) || null;
    setSelectedRole(role);

    if (role) {
      loadApplications(role.id);
    } else {
      setData(null);
    }
  };

  // ================= LOAD =================
  const loadApplications = (roleId) => {
    setRowsLoading(true);
    setError("");

    // The "no response" group is computed by the server on every call -- it
    // is every ELIGIBLE student without a decision, and eligibility changes
    // as results are published. A stored list would go stale within a day.
    API.get(`placement/roles/${roleId}/applications/`)
      .then((res) => setData(res.data))
      .catch((err) => {
        console.error("Applications error:", err.response?.data || err);
        setError("Could not load applications.");
      })
      .finally(() => setRowsLoading(false));
  };

  const counts = data?.counts || {
    applied: 0,
    opted_out: 0,
    withdrawn: 0,
    no_response: 0,
  };

  const tabs = [
    { key: "applied", label: "Applied", count: counts.applied },
    { key: "opted_out", label: "Not interested", count: counts.opted_out },
    { key: "withdrawn", label: "Withdrawn", count: counts.withdrawn },
    { key: "no_response", label: "No response", count: counts.no_response },
  ];

  const rows = data ? data[tab] || [] : [];

  const fmt = (value) =>
    value ? new Date(value).toLocaleDateString() : "—";

  return (
    <div className="app">

      <Navbar setOpen={setOpen} />

      <div className="layout">

        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">

          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">
              <h2>Applications</h2>
              <p>
                Who applied, who declined and who has not answered — per role.
              </p>
            </div>

            {/* ================= ERROR ================= */}
            {error && (
              <div
                className="card"
                style={{ borderLeft: "4px solid #dc2626", color: "#991b1b" }}
              >
                {error}
              </div>
            )}

            {/* ================= PICKERS ================= */}
            <div className="card">

              <div className="form-grid form-grid--row">

                <select
                  value={selectedDrive?.id || ""}
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
                      {` (${d.status_display})`}
                    </option>
                  ))}
                </select>

                <select
                  value={selectedRole?.id || ""}
                  onChange={(e) => selectRole(e.target.value)}
                  disabled={!selectedDrive}
                >
                  <option value="">
                    {!selectedDrive ? "Select a drive first" : "Select a role"}
                  </option>
                  {(selectedDrive?.job_roles || []).map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.title}
                      {r.package_lpa ? ` — ${r.package_lpa} LPA` : ""}
                    </option>
                  ))}
                </select>

                {selectedRole && (
                  <button
                    className="btn-edit"
                    onClick={() => loadApplications(selectedRole.id)}
                    disabled={rowsLoading}
                  >
                    {rowsLoading ? "Refreshing..." : "Refresh"}
                  </button>
                )}

              </div>

              {selectedDrive && !selectedRole && (
                <p style={{ margin: "12px 0 0", fontSize: "13px", color: "#64748b" }}>
                  Applications are per role — a student may apply for one
                  position in this drive and not another.
                </p>
              )}

            </div>

            {/* ================= RESULTS ================= */}
            {selectedRole && (
              <>

                {/* ---------- TABS ---------- */}
                <div className="card">

                  <h3>
                    {data?.company_name || selectedDrive?.company_name} —{" "}
                    {selectedRole.title}
                  </h3>

                  <div
                    style={{
                      display: "flex",
                      gap: "8px",
                      flexWrap: "wrap",
                      marginTop: "12px",
                    }}
                  >
                    {tabs.map((t) => (
                      <button
                        key={t.key}
                        className={tab === t.key ? "btn-primary" : "btn-edit"}
                        onClick={() => setTab(t.key)}
                      >
                        {t.label} ({t.count})
                      </button>
                    ))}
                  </div>

                  {counts.no_response > 0 && (
                    <p style={{ margin: "12px 0 0", fontSize: "13px", color: "#92400e" }}>
                      {counts.no_response} eligible student
                      {counts.no_response === 1 ? " has" : "s have"} not
                      answered yet.
                    </p>
                  )}

                </div>

                {/* ---------- TABLE ---------- */}
                <div className="card">

                  <h3>
                    {tabs.find((t) => t.key === tab)?.label}
                    {rowsLoading ? "" : ` (${rows.length})`}
                  </h3>

                  <table>
                    <thead>
                      <tr>
                        <th>Roll no</th>
                        <th>Student</th>
                        <th>Department</th>
                        {tab === "opted_out" && <th>Reason</th>}
                        {tab !== "no_response" && <th>Date</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {rowsLoading ? (
                        <tr>
                          <td colSpan="5">Loading...</td>
                        </tr>
                      ) : rows.length > 0 ? (
                        rows.map((r) => (
                          <tr key={r.id || r.student}>
                            <td>{r.roll_number || "—"}</td>
                            <td>{r.student_name}</td>
                            <td>{r.department_name || "—"}</td>

                            {/* The reason is the whole point of this tab. A
                                list of names without reasons tells the
                                placement cell nothing they can act on. */}
                            {tab === "opted_out" && (
                              <td>{r.opt_out_reason || "—"}</td>
                            )}

                            {tab !== "no_response" && (
                              <td>{fmt(r.updated_at || r.applied_at)}</td>
                            )}
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan="5">
                            {tab === "no_response"
                              ? "Every eligible student has answered."
                              : "Nobody in this group yet."}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>

                </div>

              </>
            )}

            {/* ================= NOTHING PICKED ================= */}
            {!selectedRole && !loading && (
              <div className="card">
                <p style={{ margin: 0 }}>
                  {drives.length === 0
                    ? "No drives yet. Create one first."
                    : "Select a drive and a role to see who applied."}
                </p>
              </div>
            )}

          </div>

        </div>

      </div>

    </div>
  );
}