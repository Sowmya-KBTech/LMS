import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

export default function PlacementOffers() {

  const [open, setOpen] = useState(false);

  const [drives, setDrives] = useState([]);
  const [drive, setDrive] = useState(null);
  const [role, setRole] = useState(null);

  const [data, setData] = useState(null);

  // ================= NEW OFFER =================
  const [application, setApplication] = useState("");
  const [packageLpa, setPackageLpa] = useState("");
  const [joiningDate, setJoiningDate] = useState("");
  const [remarks, setRemarks] = useState("");

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
    setData(null);
    resetForm();
  };

  const selectRole = (roleId) => {
    const r = (drive?.job_roles || []).find((x) => x.id === Number(roleId)) || null;
    setRole(r);
    resetForm();

    if (r) {
      // the role's advertised package is the sensible default, but the offer
      // stores its own copy -- a company can offer something different
      setPackageLpa(r.package_lpa ?? "");
      loadOffers(r.id);
    } else {
      setData(null);
    }
  };

  const resetForm = () => {
    setApplication("");
    setPackageLpa("");
    setJoiningDate("");
    setRemarks("");
  };

  // ================= LOAD =================
  const loadOffers = (roleId) => {
    setBusy(true);
    setError("");

    API.get(`placement/roles/${roleId}/offers/`)
      .then((res) => setData(res.data))
      .catch((err) => {
        console.error("Offers error:", err.response?.data || err);
        setError("Could not load offers.");
      })
      .finally(() => setBusy(false));
  };

  // ================= RECORD =================
  const handleRecord = async () => {

    if (!role) return;

    if (!application) {
      return alert("Select the student this offer is for");
    }

    setError("");
    setNotice("");

    // Plain JSON. There is no offer letter to upload -- the company sends it
    // to the student directly, so the college never holds a copy.
    const payload = {
      application: Number(application),
      package_lpa: packageLpa === "" ? null : Number(packageLpa),
      joining_date: joiningDate || null,
      remarks: remarks,
    };

    try {
      setBusy(true);

      await API.post(`placement/roles/${role.id}/offers/`, payload);

      setNotice("Offer recorded. The student can now accept or decline it.");
      resetForm();
      setPackageLpa(role.package_lpa ?? "");
      loadOffers(role.id);

    } catch (err) {
      const d = err.response?.data;
      console.error("Record offer error:", d);
      setError(d?.detail || d?.package_lpa?.[0] || "Could not record the offer.");
      setBusy(false);
    }
  };

  // ================= REMOVE =================
  const handleRemove = async (offer) => {

    if (!window.confirm(
      `Remove the offer for ${offer.student_name}? This cannot be undone.`
    )) {
      return;
    }

    setError("");
    setNotice("");

    try {
      setBusy(true);

      // A real delete, unlike everywhere else in this module. An offer
      // recorded against the wrong student is a mistake, not history, and a
      // cancelled row would still count them as placed in the reports.
      await API.delete(`placement/offers/${offer.id}/`);

      setNotice("Offer removed.");
      loadOffers(role.id);

    } catch (err) {
      console.error("Remove offer error:", err.response?.data || err);
      setError("Could not remove the offer.");
      setBusy(false);
    }
  };

  const counts = data?.counts || {};
  const noOffer = data?.no_offer || [];

  return (
    <div className="app">

      <Navbar setOpen={setOpen} />

      <div className="layout">

        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">

          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">
              <h2>Offers</h2>
              <p>
                Record who the company selected. Students accept or decline
                from their own portal.
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
                      {r.package_lpa ? ` — ${r.package_lpa} LPA` : ""}
                    </option>
                  ))}
                </select>

                {role && (
                  <button
                    className="btn-edit"
                    onClick={() => loadOffers(role.id)}
                    disabled={busy}
                  >
                    {busy ? "Refreshing..." : "Refresh"}
                  </button>
                )}

              </div>

            </div>

            {/* ================= RECORD AN OFFER ================= */}
            {role && (
              <div className="card">

                <h3>Record an offer</h3>
                <p style={{ margin: "0 0 12px", fontSize: "13px", color: "#64748b" }}>
                  Only students who applied for this role can be selected.
                </p>

                <div className="form-grid form-grid--row">

                  <select
                    value={application}
                    onChange={(e) => setApplication(e.target.value)}
                    disabled={noOffer.length === 0}
                  >
                    <option value="">
                      {noOffer.length === 0
                        ? "Everyone who applied already has an offer"
                        : "Select student *"}
                    </option>
                    {noOffer.map((s) => (
                      <option key={s.application} value={s.application}>
                        {s.roll_number} — {s.student_name}
                      </option>
                    ))}
                  </select>

                  <input
                    type="number"
                    step="0.01"
                    placeholder="Package (LPA)"
                    value={packageLpa}
                    onChange={(e) => setPackageLpa(e.target.value)}
                  />

                  <input
                    type="date"
                    title="Joining date"
                    value={joiningDate}
                    onChange={(e) => setJoiningDate(e.target.value)}
                  />

                  <input
                    placeholder="Remarks"
                    value={remarks}
                    onChange={(e) => setRemarks(e.target.value)}
                  />

                  <button
                    className="btn-primary"
                    onClick={handleRecord}
                    disabled={busy}
                  >
                    {busy ? "Saving..." : "Record offer"}
                  </button>

                </div>

                <p style={{ margin: "12px 0 0", fontSize: "13px", color: "#64748b" }}>
                  The package defaults to this role's advertised figure but is
                  stored on the offer — if the company offered something
                  different, change it here.
                </p>

              </div>
            )}

            {/* ================= OFFERS ================= */}
            {role && (
              <div className="card">

                <h3>
                  Offers — {role.title}
                  {data ? ` (${data.results?.length || 0})` : ""}
                </h3>

                {data && (
                  <p style={{ margin: "0 0 12px", fontSize: "13px", color: "#64748b" }}>
                    Waiting {counts.offered || 0} · Accepted {counts.accepted || 0} ·
                    Declined {counts.declined || 0} · No offer {counts.no_offer || 0} ·
                    Applied {counts.applied || 0}
                  </p>
                )}

                <table>
                  <thead>
                    <tr>
                      <th>Roll no</th>
                      <th>Student</th>
                      <th>Department</th>
                      <th>Package</th>
                      <th>Joining</th>
                      <th>Status</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {busy && !data ? (
                      <tr><td colSpan="7">Loading...</td></tr>
                    ) : data?.results?.length > 0 ? (
                      data.results.map((o) => (
                        <tr key={o.id}>
                          <td>{o.roll_number || "—"}</td>
                          <td>{o.student_name}</td>
                          <td>{o.department_name || "—"}</td>
                          <td>{o.package_lpa ? `${o.package_lpa} LPA` : "—"}</td>
                          <td>{o.joining_date || "—"}</td>
                          <td>
                            {o.status === "accepted" && (
                              <span style={{ color: "#166534", fontWeight: 600 }}>
                                Accepted
                              </span>
                            )}
                            {o.status === "declined" && (
                              <span style={{ color: "#991b1b" }}>Declined</span>
                            )}
                            {o.status === "offered" && (
                              <span style={{ color: "#92400e" }}>Waiting</span>
                            )}
                          </td>
                          <td>
                            <div className="action-buttons">
                              <button
                                className="btn-delete"
                                onClick={() => handleRemove(o)}
                                disabled={busy}
                              >
                                Remove
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan="7">
                          No offers recorded for this role yet.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>

                {data?.results?.length > 0 && (
                  <p style={{ margin: "12px 0 0", fontSize: "13px", color: "#64748b" }}>
                    "Waiting" means the student has not answered yet. A student
                    may hold several offers and choose between them — nothing
                    is declined automatically.
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
                    : "Select a drive and a role to record offers."}
                </p>
              </div>
            )}

          </div>

        </div>

      </div>

    </div>
  );
}