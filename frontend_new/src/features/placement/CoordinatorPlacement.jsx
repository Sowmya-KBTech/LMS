import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";
import ImportExport from "../../components/ImportExport";

import "../../App.css";

export default function CoordinatorPlacement() {

  const [open, setOpen] = useState(false);

  const [rows, setRows] = useState([]);
  const [counts, setCounts] = useState({ verified: 0, pending: 0, missing: 0 });
  const [total, setTotal] = useState(0);

  const [department, setDepartment] = useState("");

  const [filter, setFilter] = useState("");   // "" | pending | verified | missing
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");

  // ================= INIT =================
  useEffect(() => {
    // Which department this coordinator owns comes from the server, never
    // from the browser -- the same rule the API itself applies.
    API.get("placement/me/")
      .then((res) => setDepartment(res.data?.department_name || ""))
      .catch(() => setDepartment(""));
  }, []);

  useEffect(() => {
    loadList(filter);
  }, [filter]);

  const loadList = (wanted) => {
    setLoading(true);

    const url = wanted
      ? `placement/verify-academics/?status=${wanted}`
      : "placement/verify-academics/";

    API.get(url)
      .then((res) => {
        const d = res.data || {};
        setRows(d.results || []);
        // counts always cover ALL students, not just the filtered view, so
        // the tab numbers do not change as you click between them
        setCounts(d.counts || { verified: 0, pending: 0, missing: 0 });
        setTotal(d.total || 0);
      })
      .catch((err) => {
        console.error("Verification list error:", err.response?.data || err);
        setError("Could not load your students.");
      })
      .finally(() => setLoading(false));
  };

  // ================= VERIFY / UNVERIFY =================
  const setVerified = async (studentId, verified, name) => {

    if (!verified) {
      if (!window.confirm(`Send ${name}'s details back for correction?`)) {
        return;
      }
    }

    setError("");

    try {
      setBusyId(studentId);

      await API.post(`placement/verify-academics/${studentId}/`, { verified });

      // update the row in place, and move the counts, rather than refetching
      setRows((prev) =>
        prev.map((r) =>
          r.student === studentId
            ? { ...r, verified, state: verified ? "verified" : "pending" }
            : r
        )
      );

      setCounts((prev) => ({
        ...prev,
        verified: prev.verified + (verified ? 1 : -1),
        pending: prev.pending + (verified ? -1 : 1),
      }));

    } catch (err) {
      const data = err.response?.data;
      console.error("Verify error:", data);
      setError(data?.detail || "Could not update verification.");
    } finally {
      setBusyId(null);
    }
  };

  const show = (value) =>
    value === null || value === undefined || value === "" ? "—" : value;

  const tabs = [
    { key: "", label: "All", count: total },
    { key: "pending", label: "To verify", count: counts.pending },
    { key: "verified", label: "Verified", count: counts.verified },
    { key: "missing", label: "Not filled in", count: counts.missing },
  ];

  return (
    <div className="app">

      <Navbar setOpen={setOpen} />

      <div className="layout">

        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">

          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">
              <h2>Placement — My Department</h2>
              <p>
                {department
                  ? `${department} · verify the school marks your students have entered.`
                  : "Verify the school marks your students have entered."}
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

            {/* ================= FILTERS ================= */}
            <div className="card">

              <div
                style={{
                  display: "flex",
                  gap: "8px",
                  flexWrap: "wrap",
                }}
              >
                {tabs.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setFilter(t.key)}
                    className={filter === t.key ? "btn-primary" : "btn-edit"}
                  >
                    {t.label} ({t.count})
                  </button>
                ))}
              </div>

              {counts.missing > 0 && (
                <p style={{ margin: "12px 0 0", fontSize: "14px", color: "#92400e" }}>
                  {counts.missing} student{counts.missing === 1 ? "" : "s"} have not
                  entered their marks yet. They cannot apply for any drive until
                  they do.
                </p>
              )}

            </div>

            {/* ================= LIST ================= */}
            <div className="card">

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <h3>Students {loading ? "" : `(${rows.length})`}</h3>
                {/* 10th / 12th / diploma marks from Excel (meeting point 2) - your department only */}
                <ImportExport
                  importer="prior_academics"
                  label="10th / 12th marks"
                  matchLabel="roll number"
                  modes={["upsert"]}
                  align="right"
                  note="One row per student. Regular students need 10th + 12th; lateral entry needs 10th + Diploma. Verified = Yes only after checking the marksheet. Changed marks must be verified again."
                  onDone={() => loadList(filter)}
                />
              </div>

              <table>
                <thead>
                  <tr>
                    <th>Roll no</th>
                    <th>Student</th>
                    <th>10th %</th>
                    <th>12th / Diploma</th>
                    <th>Entry</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan="7">Loading...</td>
                    </tr>
                  ) : rows.length > 0 ? (
                    rows.map((r) => (
                      <tr key={r.student}>

                        <td>{show(r.roll_number)}</td>
                        <td>{show(r.student_name)}</td>

                        <td>{r.has_record ? show(r.tenth_percent) : "—"}</td>

                        <td>
                          {r.has_record ? show(r.qualifying_percent) : "—"}
                        </td>

                        <td>
                          {r.has_record
                            ? r.is_lateral_entry
                              ? "Lateral"
                              : "Regular"
                            : "—"}
                        </td>

                        <td>
                          {r.state === "verified" && (
                            <span style={{ color: "#166534" }}>Verified</span>
                          )}
                          {r.state === "pending" && (
                            <span style={{ color: "#92400e" }}>To verify</span>
                          )}
                          {r.state === "missing" && (
                            <span style={{ color: "#5D5A6B" }}>Not filled in</span>
                          )}
                        </td>

                        <td>
                          <div className="action-buttons">
                            {/* A student with no record has nothing to check --
                                showing a Verify button there would only produce
                                an error from the API. */}
                            {!r.has_record ? (
                              <span style={{ fontSize: "14px", color: "#5D5A6B" }}>
                                Waiting on student
                              </span>
                            ) : r.verified ? (
                              <button
                                className="btn-delete"
                                onClick={() =>
                                  setVerified(r.student, false, r.student_name)
                                }
                                disabled={busyId === r.student}
                              >
                                Undo
                              </button>
                            ) : (
                              <button
                                className="btn-primary"
                                onClick={() =>
                                  setVerified(r.student, true, r.student_name)
                                }
                                disabled={busyId === r.student}
                              >
                                {busyId === r.student ? "..." : "Verify"}
                              </button>
                            )}
                          </div>
                        </td>

                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="7">
                        {filter
                          ? "No students in this group."
                          : "No students in your department."}
                      </td>
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