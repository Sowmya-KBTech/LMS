import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

const STATUSES = [
  { value: "draft", label: "Draft" },
  { value: "published", label: "Published" },
  { value: "closed", label: "Closed" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

export default function PlacementDrives() {

  const [open, setOpen] = useState(false);

  const [drives, setDrives] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [departments, setDepartments] = useState([]);

  // ================= NEW DRIVE =================
  // The visit only. Roles are added afterwards, because one visit can open
  // several positions at different packages.
  const [company, setCompany] = useState("");
  const [driveTitle, setDriveTitle] = useState("");
  const [deadline, setDeadline] = useState("");
  const [driveDate, setDriveDate] = useState("");

  // ================= SELECTION =================
  const [selectedDrive, setSelectedDrive] = useState(null);
  const [selectedRole, setSelectedRole] = useState(null);

  const [matches, setMatches] = useState(null);
  const [matchLoading, setMatchLoading] = useState(false);

  // ================= NEW ROLE =================
  const [roleTitle, setRoleTitle] = useState("");
  const [rolePackage, setRolePackage] = useState("");
  const [roleLocation, setRoleLocation] = useState("");
  const [roleOpenings, setRoleOpenings] = useState("");
  const [roleBond, setRoleBond] = useState("");

  // ================= ELIGIBILITY =================
  const [minCgpa, setMinCgpa] = useState("");
  const [maxArrears, setMaxArrears] = useState("");
  const [minTenth, setMinTenth] = useState("");
  const [minTwelfth, setMinTwelfth] = useState("");
  const [passingYear, setPassingYear] = useState("");
  const [allowLateral, setAllowLateral] = useState(true);
  const [placedCap, setPlacedCap] = useState("");
  const [allowedDepts, setAllowedDepts] = useState([]);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // ================= INIT =================
  useEffect(() => {
    loadDrives();

    API.get("placement/companies/?active=true")
      .then((res) => setCompanies(res.data || []))
      .catch((err) => console.error("Companies error:", err));

    API.get("placement/departments/")
      .then((res) => setDepartments(res.data || []))
      .catch((err) => console.error("Departments error:", err));
  }, []);

  const loadDrives = () => {
    setLoading(true);

    API.get("placement/drives/")
      .then((res) => setDrives(res.data || []))
      .catch((err) => {
        console.error("Drives error:", err.response?.data || err);
        setError("Could not load drives.");
      })
      .finally(() => setLoading(false));
  };

  // Refetch one drive after a change, rather than patching local state by
  // hand: roles and eligibility hang off it, and rebuilding that shape in the
  // browser is where the two versions drift apart.
  const refreshDrive = async (driveId, keepRoleId = null) => {
    const res = await API.get(`placement/drives/${driveId}/`);
    const fresh = res.data;

    setSelectedDrive(fresh);
    setDrives((prev) => prev.map((d) => (d.id === driveId ? fresh : d)));

    if (keepRoleId) {
      const role = (fresh.job_roles || []).find((r) => r.id === keepRoleId);
      if (role) {
        setSelectedRole(role);
      }
    }

    return fresh;
  };

  // ================= CREATE DRIVE =================
  const handleCreateDrive = async () => {

    setError("");

    if (!company) {
      return alert("Select a company");
    }

    const payload = {
      company: Number(company),
      title: driveTitle.trim(),
      // datetime-local gives "2026-08-14T17:00", which Django parses directly
      application_deadline: deadline || null,
      drive_date: driveDate || null,
      status: "draft",
    };

    try {
      setSaving(true);

      const res = await API.post("placement/drives/", payload);
      setDrives((prev) => [res.data, ...prev]);

      setCompany("");
      setDriveTitle("");
      setDeadline("");
      setDriveDate("");

      // open it straight away -- a drive with no roles cannot be published,
      // so the next step is always adding one
      setSelectedDrive(res.data);
      setSelectedRole(null);

    } catch (err) {
      const data = err.response?.data;
      console.error("Create drive error:", data);
      setError(
        data?.application_deadline?.[0] ||
        data?.company?.[0] ||
        data?.detail ||
        "Could not create the drive."
      );
    } finally {
      setSaving(false);
    }
  };

  // ================= SELECT =================
  const selectDrive = (d) => {
    setError("");
    setSelectedDrive(d);
    setSelectedRole(null);
    setMatches(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const selectRole = (role) => {
    setError("");
    setSelectedRole(role);

    const e = role.eligibility || {};
    setMinCgpa(e.min_cgpa ?? "");
    setMaxArrears(e.max_arrears ?? "");
    setMinTenth(e.min_tenth_percent ?? "");
    setMinTwelfth(e.min_twelfth_percent ?? "");
    setPassingYear(e.passing_year ?? "");
    setAllowLateral(e.allow_lateral_entry !== false);
    setPlacedCap(e.placed_package_cap ?? "");
    setAllowedDepts(e.allowed_departments || []);

    loadMatches(role.id);
  };

  // ================= LIVE MATCH COUNT =================
  const loadMatches = (roleId) => {
    setMatchLoading(true);

    // Per ROLE. Computed by the server on every call and never cached here --
    // the whole point is that it reflects results and verifications as they
    // change.
    API.get(`placement/roles/${roleId}/matches/`)
      .then((res) => setMatches(res.data))
      .catch((err) => console.error("Matches error:", err.response?.data || err))
      .finally(() => setMatchLoading(false));
  };

  // ================= ADD ROLE =================
  const handleAddRole = async () => {

    if (!selectedDrive) return;

    if (!roleTitle.trim()) {
      return alert("Enter the role title");
    }

    setError("");

    try {
      setSaving(true);

      const res = await API.post(
        `placement/drives/${selectedDrive.id}/roles/`,
        {
          title: roleTitle.trim(),
          package_lpa: rolePackage ? Number(rolePackage) : null,
          job_location: roleLocation,
          openings: roleOpenings ? Number(roleOpenings) : null,
          bond_details: roleBond,
        }
      );

      await refreshDrive(selectedDrive.id);
      selectRole(res.data);

      setRoleTitle("");
      setRolePackage("");
      setRoleLocation("");
      setRoleOpenings("");
      setRoleBond("");

    } catch (err) {
      const data = err.response?.data;
      console.error("Add role error:", data);
      setError(
        data?.title?.[0] ||
        data?.non_field_errors?.[0] ||
        data?.detail ||
        "Could not add the role."
      );
    } finally {
      setSaving(false);
    }
  };

  const handleDeactivateRole = async (role) => {

    if (!window.confirm(`Deactivate ${role.title}?`)) return;

    try {
      setSaving(true);

      await API.delete(`placement/roles/${role.id}/`);
      await refreshDrive(selectedDrive.id);

      if (selectedRole?.id === role.id) {
        setSelectedRole(null);
        setMatches(null);
      }

    } catch (err) {
      console.error("Deactivate role error:", err.response?.data || err);
      setError("Could not deactivate the role.");
    } finally {
      setSaving(false);
    }
  };

  // ================= SAVE ELIGIBILITY =================
  const handleSaveEligibility = async () => {

    if (!selectedRole) return;
    setError("");

    // Blank means "no limit on this", which is null -- NOT 0. A min_cgpa of 0
    // and an unset min_cgpa are different rules, and sending 0 would quietly
    // turn "don't care" into a real cutoff.
    const numOrNull = (v) => (v === "" || v === null ? null : Number(v));

    const payload = {
      min_cgpa: numOrNull(minCgpa),
      max_arrears: numOrNull(maxArrears),
      min_tenth_percent: numOrNull(minTenth),
      min_twelfth_percent: numOrNull(minTwelfth),
      passing_year: numOrNull(passingYear),
      allow_lateral_entry: allowLateral,
      placed_package_cap: numOrNull(placedCap),
      allowed_departments: allowedDepts.map(Number),
    };

    try {
      setSaving(true);

      await API.patch(
        `placement/roles/${selectedRole.id}/eligibility/`,
        payload
      );

      await refreshDrive(selectedDrive.id, selectedRole.id);

      // the rules changed, so the count is stale
      loadMatches(selectedRole.id);

    } catch (err) {
      console.error("Eligibility error:", err.response?.data || err);
      setError("Could not save eligibility.");
    } finally {
      setSaving(false);
    }
  };

  // ================= STATUS =================
  const handleStatus = async (newStatus) => {

    if (!selectedDrive) return;
    setError("");

    // Publishing a drive with no roles would show students a card with
    // nothing to apply for.
    if (newStatus === "published" && !(selectedDrive.job_roles || []).length) {
      return setError("Add at least one role before publishing this drive.");
    }

    try {
      setSaving(true);

      await API.patch(`placement/drives/${selectedDrive.id}/`, {
        status: newStatus,
      });

      await refreshDrive(selectedDrive.id, selectedRole?.id);

    } catch (err) {
      console.error("Status error:", err.response?.data || err);
      setError("Could not change the status.");
    } finally {
      setSaving(false);
    }
  };

  const toggleDept = (id) => {
    setAllowedDepts((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const roles = selectedDrive?.job_roles || [];

  return (
    <div className="app">

      <Navbar setOpen={setOpen} />

      <div className="layout">

        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">

          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">
              <h2>Drives</h2>
              <p>
                A drive is one company visit. Add the roles on offer, set who
                can apply for each, then publish it.
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

            {/* ================= NEW DRIVE ================= */}
            <div className="card">

              <h3>New Drive</h3>
              <p style={{ margin: "0 0 12px", fontSize: "13px", color: "#64748b" }}>
                The visit itself. Roles and packages are added next.
              </p>

              <div className="form-grid form-grid--row">

                <select
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                >
                  <option value="">Select Company *</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>

                <input
                  placeholder="Title (e.g. 2026 Campus Drive)"
                  value={driveTitle}
                  onChange={(e) => setDriveTitle(e.target.value)}
                />

                <input
                  type="datetime-local"
                  title="Applications close"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                />

                <input
                  type="date"
                  title="Drive date"
                  value={driveDate}
                  onChange={(e) => setDriveDate(e.target.value)}
                />

                <button
                  className="btn-primary"
                  onClick={handleCreateDrive}
                  disabled={saving}
                >
                  {saving ? "Saving..." : "Create as draft"}
                </button>

              </div>

            </div>

            {/* ================= SELECTED DRIVE ================= */}
            {selectedDrive && (
              <>

                {/* ---------- SUMMARY ---------- */}
                <div className="card">

                  <h3>
                    {selectedDrive.company_name}
                    {selectedDrive.title ? ` — ${selectedDrive.title}` : ""}
                  </h3>

                  <p style={{ margin: "6px 0 12px", color: "#64748b" }}>
                    {selectedDrive.status_display}
                    {selectedDrive.is_open ? " · open for applications" : " · not open"}
                    {" · "}
                    {roles.length} role{roles.length === 1 ? "" : "s"}
                    {selectedDrive.drive_date
                      ? ` · Drive on ${selectedDrive.drive_date}`
                      : " · no drive date set"}
                  </p>

                  <div className="action-buttons">
                    {STATUSES.map((s) => (
                      <button
                        key={s.value}
                        className={
                          selectedDrive.status === s.value ? "btn-primary" : "btn-edit"
                        }
                        onClick={() => handleStatus(s.value)}
                        disabled={saving || selectedDrive.status === s.value}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>

                  <p style={{ margin: "12px 0 0", fontSize: "13px", color: "#64748b" }}>
                    Students see a drive only once it is Published.
                  </p>

                </div>

                {/* ---------- ROLES ---------- */}
                <div className="card">

                  <h3>Roles ({roles.length})</h3>
                  <p style={{ margin: "0 0 12px", fontSize: "13px", color: "#64748b" }}>
                    Each role has its own package and its own eligibility.
                  </p>

                  <div className="form-grid form-grid--row">

                    <input
                      placeholder="Role title *"
                      value={roleTitle}
                      onChange={(e) => setRoleTitle(e.target.value)}
                    />

                    <input
                      type="number"
                      step="0.01"
                      placeholder="Package (LPA)"
                      value={rolePackage}
                      onChange={(e) => setRolePackage(e.target.value)}
                    />

                    <input
                      placeholder="Location"
                      value={roleLocation}
                      onChange={(e) => setRoleLocation(e.target.value)}
                    />

                    <input
                      type="number"
                      min="1"
                      placeholder="Openings"
                      value={roleOpenings}
                      onChange={(e) => setRoleOpenings(e.target.value)}
                    />

                    <input
                      placeholder="Bond"
                      value={roleBond}
                      onChange={(e) => setRoleBond(e.target.value)}
                    />

                    <button
                      className="btn-primary"
                      onClick={handleAddRole}
                      disabled={saving}
                    >
                      Add role
                    </button>

                  </div>

                  <table style={{ marginTop: "14px" }}>
                    <thead>
                      <tr>
                        <th>Role</th>
                        <th>Package</th>
                        <th>Location</th>
                        <th>Openings</th>
                        <th>Status</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {roles.length > 0 ? (
                        roles.map((r) => (
                          <tr
                            key={r.id}
                            style={
                              selectedRole?.id === r.id
                                ? { background: "#eff6ff" }
                                : undefined
                            }
                          >
                            <td>{r.title}</td>
                            <td>{r.package_lpa ? `${r.package_lpa} LPA` : "—"}</td>
                            <td>{r.job_location || "—"}</td>
                            <td>{r.openings ?? "—"}</td>
                            <td>
                              {r.is_active ? (
                                <span style={{ color: "#166534" }}>Active</span>
                              ) : (
                                <span style={{ color: "#64748b" }}>Inactive</span>
                              )}
                            </td>
                            <td>
                              <div className="action-buttons">
                                <button
                                  className="btn-edit"
                                  onClick={() => selectRole(r)}
                                >
                                  Eligibility
                                </button>
                                {r.is_active && (
                                  <button
                                    className="btn-delete"
                                    onClick={() => handleDeactivateRole(r)}
                                    disabled={saving}
                                  >
                                    Deactivate
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))
                      ) : (
                        <tr>
                          <td colSpan="6">
                            No roles yet. Add one before publishing.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>

                </div>

                {/* ---------- SELECTED ROLE ---------- */}
                {selectedRole && (
                  <>

                    {/* ....... MATCHES ....... */}
                    <div className="card">

                      <h3>Who matches — {selectedRole.title}</h3>

                      {matchLoading ? (
                        <p>Counting...</p>
                      ) : matches ? (
                        <>
                          <p style={{ fontSize: "15px" }}>
                            <strong>{matches.eligible}</strong> of{" "}
                            {matches.total_students} students are eligible for
                            this role.
                          </p>

                          {matches.reasons?.length > 0 && (
                            <>
                              <p style={{ margin: "12px 0 6px", fontWeight: 600 }}>
                                Why the rest are not:
                              </p>
                              <table>
                                <thead>
                                  <tr>
                                    <th>Reason</th>
                                    <th>Students</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {matches.reasons.map((r) => (
                                    <tr key={r.reason}>
                                      <td>{r.reason}</td>
                                      <td>{r.count}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </>
                          )}
                        </>
                      ) : (
                        <p>—</p>
                      )}

                    </div>

                    {/* ....... ELIGIBILITY ....... */}
                    <div className="card">

                      <h3>Eligibility — {selectedRole.title}</h3>

                      <p style={{ margin: "0 0 12px", fontSize: "13px", color: "#64748b" }}>
                        Leave a box blank for no limit on that criterion. These
                        rules apply to this role only.
                      </p>

                      <div className="form-grid form-grid--row">

                        <input
                          type="number"
                          step="0.01"
                          placeholder="Min CGPA"
                          value={minCgpa}
                          onChange={(e) => setMinCgpa(e.target.value)}
                        />

                        <input
                          type="number"
                          min="0"
                          placeholder="Max arrears"
                          value={maxArrears}
                          onChange={(e) => setMaxArrears(e.target.value)}
                        />

                        <input
                          type="number"
                          step="0.01"
                          placeholder="Min 10th %"
                          value={minTenth}
                          onChange={(e) => setMinTenth(e.target.value)}
                        />

                        <input
                          type="number"
                          step="0.01"
                          placeholder="Min 12th / Diploma %"
                          value={minTwelfth}
                          onChange={(e) => setMinTwelfth(e.target.value)}
                        />

                        <input
                          type="number"
                          placeholder="Passing year"
                          value={passingYear}
                          onChange={(e) => setPassingYear(e.target.value)}
                        />

                        <label
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "6px",
                            fontSize: "14px",
                            color: "#334155",
                            whiteSpace: "nowrap",
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={allowLateral}
                            onChange={(e) => setAllowLateral(e.target.checked)}
                          />
                          Allow lateral entry
                        </label>

                      </div>

                      {/* ....... ALREADY PLACED ....... */}
                      <p style={{ margin: "14px 0 6px", fontWeight: 600 }}>
                        Already placed
                      </p>
                      <p style={{ margin: "0 0 8px", fontSize: "13px", color: "#64748b" }}>
                        A student holding an <strong>accepted</strong> offer at
                        or above this package cannot apply. Leave blank if an
                        offer should never block them.
                      </p>

                      <div className="form-grid form-grid--row">
                        <input
                          type="number"
                          step="0.01"
                          placeholder="Package cap (LPA), e.g. 6"
                          value={placedCap}
                          onChange={(e) => setPlacedCap(e.target.value)}
                        />
                      </div>

                      <p style={{ margin: "14px 0 6px", fontWeight: 600 }}>
                        Branches
                      </p>
                      <p style={{ margin: "0 0 8px", fontSize: "13px", color: "#64748b" }}>
                        Select none to open this role to every branch.
                      </p>

                      <div style={{ display: "flex", gap: "14px", flexWrap: "wrap" }}>
                        {departments.map((d) => (
                          <label
                            key={d.id}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: "6px",
                              fontSize: "14px",
                              color: "#334155",
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={allowedDepts.includes(d.id)}
                              onChange={() => toggleDept(d.id)}
                            />
                            {d.code || d.name}
                          </label>
                        ))}
                      </div>

                      <div style={{ marginTop: "14px" }}>
                        <button
                          className="btn-primary"
                          onClick={handleSaveEligibility}
                          disabled={saving}
                        >
                          {saving ? "Saving..." : "Save eligibility"}
                        </button>
                      </div>

                    </div>

                  </>
                )}

              </>
            )}

            {/* ================= ALL DRIVES ================= */}
            <div className="card">

              <h3>All drives {loading ? "" : `(${drives.length})`}</h3>

              <table>
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Title</th>
                    <th>Roles</th>
                    <th>Deadline</th>
                    <th>Drive date</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan="7">Loading...</td>
                    </tr>
                  ) : drives.length > 0 ? (
                    drives.map((d) => (
                      <tr key={d.id}>
                        <td>{d.company_name}</td>
                        <td>{d.title || "—"}</td>
                        <td>{d.job_roles?.length || 0}</td>
                        <td>
                          {d.application_deadline
                            ? new Date(d.application_deadline).toLocaleString()
                            : "—"}
                        </td>
                        <td>{d.drive_date || "—"}</td>
                        <td>
                          {d.is_open ? (
                            <span style={{ color: "#166534" }}>Open</span>
                          ) : (
                            <span style={{ color: "#64748b" }}>
                              {d.status_display}
                            </span>
                          )}
                        </td>
                        <td>
                          <div className="action-buttons">
                            <button
                              className="btn-edit"
                              onClick={() => selectDrive(d)}
                            >
                              Manage
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="7">No drives yet.</td>
                    </tr>
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