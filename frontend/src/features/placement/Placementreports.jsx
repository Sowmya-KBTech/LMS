import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

export default function PlacementReports() {

  const [open, setOpen] = useState(false);

  const [data, setData] = useState(null);
  const [year, setYear] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // ================= INIT =================
  useEffect(() => {
    load();
  }, []);

  const load = (wanted) => {
    setLoading(true);
    setError("");

    const url = wanted
      ? `placement/report/?year=${wanted}`
      : "placement/report/";

    API.get(url)
      .then((res) => {
        setData(res.data);
        setYear(res.data?.year || "");
      })
      .catch((err) => {
        console.error("Report error:", err.response?.data || err);
        setError("Could not load the report.");
      })
      .finally(() => setLoading(false));
  };

  const summary = data?.summary || {};
  const pkg = data?.package || {};

  const fig = (value, suffix = "") =>
    value === null || value === undefined ? "—" : `${value}${suffix}`;

  return (
    <div className="app">

      <Navbar setOpen={setOpen} />

      <div className="layout">

        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">

          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">
              <h2>Placement report</h2>
              <p>
                One graduating batch at a time. Figures update as offers are
                recorded and accepted.
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

            {/* ================= YEAR ================= */}
            <div className="card">

              <div className="form-grid form-grid--row">

                <select
                  value={year}
                  onChange={(e) => {
                    setYear(e.target.value);
                    load(e.target.value);
                  }}
                  disabled={loading}
                >
                  {(data?.years || []).map((y) => (
                    <option key={y} value={y}>
                      Passing out {y}
                    </option>
                  ))}
                </select>

                <button
                  className="btn-edit"
                  onClick={() => load(year)}
                  disabled={loading}
                >
                  {loading ? "Loading..." : "Refresh"}
                </button>

              </div>

              {data?.detail && (
                <p style={{ margin: "12px 0 0", fontSize: "13px", color: "#92400e" }}>
                  {data.detail}
                </p>
              )}

            </div>

            {/* ================= SUMMARY ================= */}
            <div className="card">

              <h3>Summary</h3>

              <div style={{ display: "flex", gap: "28px", flexWrap: "wrap" }}>

                <div>
                  <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                    Students
                  </p>
                  <p style={{ margin: "4px 0 0", fontSize: "24px", fontWeight: 600 }}>
                    {fig(summary.students)}
                  </p>
                </div>

                <div>
                  <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                    Placed
                  </p>
                  <p
                    style={{
                      margin: "4px 0 0",
                      fontSize: "24px",
                      fontWeight: 600,
                      color: "#166534",
                    }}
                  >
                    {fig(summary.placed)}
                  </p>
                </div>

                <div>
                  <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                    Placement rate
                  </p>
                  <p style={{ margin: "4px 0 0", fontSize: "24px", fontWeight: 600 }}>
                    {fig(summary.percent, "%")}
                  </p>
                </div>

                <div>
                  <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                    Not placed
                  </p>
                  <p style={{ margin: "4px 0 0", fontSize: "24px", fontWeight: 600 }}>
                    {fig(summary.not_placed)}
                  </p>
                </div>

                <div>
                  <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                    Applied
                  </p>
                  <p style={{ margin: "4px 0 0", fontSize: "24px", fontWeight: 600 }}>
                    {fig(summary.applied)}
                  </p>
                </div>

              </div>

              {/* The distinction the whole report rests on. Stated on screen
                  because someone reading "12 placed, 18 offers" will
                  otherwise assume one of the numbers is wrong. */}
              <p style={{ margin: "16px 0 0", fontSize: "13px", color: "#64748b" }}>
                <strong>{fig(summary.placed)}</strong> students hold{" "}
                <strong>{fig(summary.accepted_offers)}</strong> accepted offer
                {summary.accepted_offers === 1 ? "" : "s"} between them. A
                student with two offers is still one placed student — this is
                the figure to publish.
              </p>

            </div>

            {/* ================= PACKAGE ================= */}
            <div className="card">

              <h3>Package</h3>

              <div style={{ display: "flex", gap: "28px", flexWrap: "wrap" }}>

                <div>
                  <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                    Highest
                  </p>
                  <p style={{ margin: "4px 0 0", fontSize: "24px", fontWeight: 600 }}>
                    {fig(pkg.highest, " LPA")}
                  </p>
                </div>

                <div>
                  <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                    Average
                  </p>
                  <p style={{ margin: "4px 0 0", fontSize: "24px", fontWeight: 600 }}>
                    {fig(pkg.average, " LPA")}
                  </p>
                </div>

                <div>
                  <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                    Lowest
                  </p>
                  <p style={{ margin: "4px 0 0", fontSize: "24px", fontWeight: 600 }}>
                    {fig(pkg.lowest, " LPA")}
                  </p>
                </div>

              </div>

              <p style={{ margin: "14px 0 0", fontSize: "13px", color: "#64748b" }}>
                Based on {fig(pkg.counted)} student
                {pkg.counted === 1 ? "" : "s"}. Where a student accepted more
                than one offer, the higher package is counted.
              </p>

            </div>

            {/* ================= BY DEPARTMENT ================= */}
            <div className="card">

              <h3>By department</h3>

              <table>
                <thead>
                  <tr>
                    <th>Department</th>
                    <th>Students</th>
                    <th>Placed</th>
                    <th>Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan="4">Loading...</td></tr>
                  ) : data?.departments?.length > 0 ? (
                    data.departments.map((d) => (
                      <tr key={d.department}>
                        <td>{d.department}</td>
                        <td>{d.students}</td>
                        <td>{d.placed}</td>
                        <td>{d.percent}%</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="4">No students in this batch.</td>
                    </tr>
                  )}
                </tbody>
              </table>

            </div>

            {/* ================= BY COMPANY TYPE ================= */}
            <div className="card">

              <h3>By company type</h3>

              <table>
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Offers</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan="2">Loading...</td></tr>
                  ) : data?.categories?.length > 0 ? (
                    data.categories.map((c) => (
                      <tr key={c.category}>
                        <td>{c.category}</td>
                        <td>{c.offers}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="2">No offers accepted in this batch yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>

              {/* Counts OFFERS, not students -- a student with a product and
                  a service offer appears in both rows. Said plainly so the
                  numbers are not misread as students. */}
              {data?.categories?.length > 0 && (
                <p style={{ margin: "12px 0 0", fontSize: "13px", color: "#64748b" }}>
                  Counts accepted offers, not students — a student holding two
                  offers appears in both rows.
                </p>
              )}

            </div>

            {/* ================= BY COMPANY ================= */}
            <div className="card">

              <h3>By company</h3>

              <table>
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Offers accepted</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr><td colSpan="2">Loading...</td></tr>
                  ) : data?.companies?.length > 0 ? (
                    data.companies.map((c) => (
                      <tr key={c.company}>
                        <td>{c.company}</td>
                        <td>{c.offers}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan="2">No offers accepted in this batch yet.</td>
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