import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

export default function PlacementDashboard() {

  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    API.get("placement/dashboard/")
      .then((res) => setData(res.data))
      .catch((err) => {
        console.error("Dashboard error:", err.response?.data || err);
        setError("Could not load the dashboard.");
      })
      .finally(() => setLoading(false));
  }, []);

  const counts = data?.counts || {};
  const attention = data?.attention || [];
  const openRoles = data?.open_drives || [];
  const offers = data?.recent_offers || [];

  const fmtDeadline = (value) =>
    value ? new Date(value).toLocaleString() : "No deadline";

  // Days left, so "closes in 2 days" reads faster than a date the officer has
  // to compare against today.
  const daysLeft = (value) => {
    if (!value) return null;
    const diff = new Date(value) - new Date();
    return Math.ceil(diff / (1000 * 60 * 60 * 24));
  };

  const Figure = ({ label, value, colour, onClick }) => (
    <div
      onClick={onClick}
      style={{
        cursor: onClick ? "pointer" : "default",
        minWidth: "110px",
      }}
    >
      <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>{label}</p>
      <p
        style={{
          margin: "4px 0 0",
          fontSize: "26px",
          fontWeight: 600,
          color: colour || "#0f172a",
        }}
      >
        {value ?? "—"}
      </p>
    </div>
  );

  return (
    <div className="app">

      <Navbar setOpen={setOpen} />

      <div className="layout">

        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">

          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">
              <h2>Placement</h2>
              <p>What is open, and what needs your attention.</p>
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

            {/* ================= NEEDS ATTENTION ================= */}
            {/* First on the page, before the figures. Each of these is a
                SILENT problem -- nothing errors and nothing looks broken, the
                drive simply does nothing. They are the reason this page
                exists. */}
            {!loading && attention.length > 0 && (
              <div
                className="card"
                style={{ borderLeft: "4px solid #ca8a04" }}
              >
                <h3 style={{ color: "#92400e" }}>
                  Needs attention ({attention.length})
                </h3>

                {attention.map((a, i) => (
                  <p
                    key={i}
                    style={{
                      margin: i === 0 ? "8px 0 0" : "10px 0 0",
                      fontSize: "14px",
                      color: "#92400e",
                    }}
                  >
                    · {a.message}
                    {a.kind === "no_roles" && (
                      <button
                        className="btn-edit"
                        style={{ marginLeft: "10px" }}
                        onClick={() => navigate("/placement/drives")}
                      >
                        Add roles
                      </button>
                    )}
                    {a.kind === "nobody_eligible" && (
                      <button
                        className="btn-edit"
                        style={{ marginLeft: "10px" }}
                        onClick={() => navigate("/placement/drives")}
                      >
                        Check cutoffs
                      </button>
                    )}
                  </p>
                ))}
              </div>
            )}

            {!loading && attention.length === 0 && (
              <div
                className="card"
                style={{ borderLeft: "4px solid #16a34a" }}
              >
                <p style={{ margin: 0, color: "#166534" }}>
                  Nothing needs attention right now.
                </p>
              </div>
            )}

            {/* ================= FIGURES ================= */}
            <div className="card">

              <h3>At a glance</h3>

              <div style={{ display: "flex", gap: "30px", flexWrap: "wrap" }}>
                <Figure label="Students" value={counts.students} />
                <Figure
                  label="Unverified"
                  value={counts.unverified}
                  colour={counts.unverified > 0 ? "#92400e" : undefined}
                />
                <Figure label="Open roles" value={counts.open_roles} />
                <Figure label="Drives" value={counts.drives} />
                <Figure label="Companies" value={counts.companies} />
                <Figure
                  label="Offers waiting"
                  value={counts.offers_waiting}
                  colour={counts.offers_waiting > 0 ? "#92400e" : undefined}
                />
              </div>

              {counts.unverified > 0 && (
                <p style={{ margin: "16px 0 0", fontSize: "13px", color: "#64748b" }}>
                  An unverified student is ineligible for every role, whatever
                  their marks. Coordinators verify their own department.
                </p>
              )}

            </div>

            {/* ================= OPEN ROLES ================= */}
            <div className="card">

              <h3>Open for applications {loading ? "" : `(${openRoles.length})`}</h3>

              <table>
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Role</th>
                    <th>Package</th>
                    <th>Eligible</th>
                    <th>Applied</th>
                    <th>Closes</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan="6">Loading...</td></tr>
                  ) : openRoles.length > 0 ? (
                    openRoles.map((r) => {
                      const days = daysLeft(r.application_deadline);
                      return (
                        <tr key={`${r.drive}-${r.role}`}>
                          <td>{r.company_name}</td>
                          <td>{r.role_title}</td>
                          <td>{r.package_lpa ? `${r.package_lpa} LPA` : "—"}</td>
                          <td
                            style={
                              r.eligible === 0
                                ? { color: "#991b1b", fontWeight: 600 }
                                : undefined
                            }
                          >
                            {r.eligible}
                          </td>
                          <td>{r.applied}</td>
                          <td>
                            {days === null ? (
                              "No deadline"
                            ) : days <= 3 ? (
                              <span style={{ color: "#991b1b" }}>
                                {days <= 0 ? "Today" : `${days} day${days === 1 ? "" : "s"}`}
                              </span>
                            ) : (
                              fmtDeadline(r.application_deadline)
                            )}
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan="6">
                        No roles are open for applications.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>

            </div>

            {/* ================= RECENT OFFERS ================= */}
            <div className="card">

              <h3>Recent offers</h3>

              <table>
                <thead>
                  <tr>
                    <th>Roll no</th>
                    <th>Student</th>
                    <th>Company</th>
                    <th>Role</th>
                    <th>Package</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan="6">Loading...</td></tr>
                  ) : offers.length > 0 ? (
                    offers.map((o) => (
                      <tr key={o.id}>
                        <td>{o.roll_number || "—"}</td>
                        <td>{o.student_name}</td>
                        <td>{o.company_name}</td>
                        <td>{o.role_title}</td>
                        <td>{o.package_lpa ? `${o.package_lpa} LPA` : "—"}</td>
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
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="6">No offers recorded yet.</td>
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