// frontend/src/features/mentoring/HodMentorAllocation.jsx
import { useCallback, useEffect, useMemo, useState } from "react";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import MentoringTabs from "./MentoringTabs";

import {
  assignMentor,
  autoDistribute,
  bandClass,
  decideProposals,
  errorText,
  getAllocations,
  getOptions,
  getProposals,
  getSplitPreview,
  getSuggestion,
  prettyYear,
  removeAllocation,
  statusPill,
  yearLabel,
} from "./mentoringApi";

import "../../App.css";
import "../../styles/MentorAllocation.css";

const EMPTY_FILTERS = {
  year: "all",
  course: "all",
  band: "all",
  mentor: "all",
  status: "all",
  q: "",
};

export default function HodMentorAllocation() {
  const [open, setOpen] = useState(false);

  // ================= CONTEXT =================
  const [options, setOptions] = useState(null);
  const [department, setDepartment] = useState("");
  const [academicYear, setAcademicYear] = useState("");

  // ================= DATA =================
  const [rows, setRows] = useState([]);
  const [mentors, setMentors] = useState([]);
  const [batches, setBatches] = useState([]);
  const [pool, setPool] = useState(null);

  // ================= UI =================
  const [view, setView] = useState("proposals"); // proposals | students
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [search, setSearch] = useState(""); // what is typed; debounced into filters.q
  const [selected, setSelected] = useState({});
  const [openBatch, setOpenBatch] = useState({});
  const [bulkMentor, setBulkMentor] = useState("");
  const [preview, setPreview] = useState(null);
  const [why, setWhy] = useState(null);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  const flash = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  };

  // ================= LOAD =================
  const loadOptions = useCallback(async () => {
    try {
      const data = await getOptions();
      setOptions(data);
      if (!academicYear && data.academic_years?.length) {
        setAcademicYear(data.academic_years[0]);
      }
    } catch (err) {
      setError(errorText(err, "Could not load filter options. Are you an HOD?"));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadAll = useCallback(
    async (ay, f) => {
      if (!ay) return;
      setLoading(true);
      setError("");
      try {
        const [alloc, props] = await Promise.all([
          getAllocations({ ...f, academic_year: ay }),
          getProposals({ academic_year: ay }),
        ]);
        setRows(alloc.results || []);
        setMentors(alloc.mentors || []);
        setDepartment(alloc.department?.name || "");
        setBatches(props.batches || []);
        setPool(props.pool || null);
      } catch (err) {
        setError(errorText(err, "Could not load allocations."));
        setRows([]);
        setMentors([]);
        setBatches([]);
        setPool(null);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    loadOptions();
  }, [loadOptions]);

  // One request per pause in typing, not one per keystroke. With 400+ students
  // an un-debounced search box fires a query on every letter.
  useEffect(() => {
    const t = setTimeout(
      () => setFilters((prev) => (prev.q === search ? prev : { ...prev, q: search })),
      350
    );
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    loadAll(academicYear, filters);
  }, [academicYear, filters, loadAll]);

  const refresh = () => loadAll(academicYear, filters);

  // ================= DERIVED =================
  const counts = useMemo(() => {
    const active = rows.filter((r) => r.status === "active").length;
    const pending = rows.filter((r) => r.status === "pending").length;
    const none = rows.filter((r) => r.status === "none").length;
    return { active, pending, none, total: rows.length };
  }, [rows]);

  const selectedIds = useMemo(
    () => Object.keys(selected).filter((k) => selected[k]).map(Number),
    [selected]
  );

  const selectedRows = useMemo(
    () => rows.filter((r) => selected[r.student_id]),
    [rows, selected]
  );

  const toggleOne = (id) =>
    setSelected((prev) => ({ ...prev, [id]: !prev[id] }));

  const toggleAll = () => {
    const all = rows.length > 0 && rows.every((r) => selected[r.student_id]);
    const next = {};
    rows.forEach((r) => {
      next[r.student_id] = !all;
    });
    setSelected(next);
  };

  // ================= ACTIONS =================
  const doAssign = async (studentIds, mentorId, override = false) => {
    if (!studentIds.length) {
      flash("Tick at least one student first.");
      return;
    }
    if (!mentorId) {
      flash("Choose a mentor first.");
      return;
    }
    setBusy(true);
    try {
      const data = await assignMentor({
        student_ids: studentIds,
        mentor_id: Number(mentorId),
        academic_year: academicYear,
        override,
      });
      flash(`Assigned ${data.assigned} student(s) to ${data.mentor}`);
      setSelected({});
      await refresh();
    } catch (err) {
      // 409 = capacity warning, not a failure. Ask, then repeat with override.
      if (err?.response?.status === 409) {
        const msg = err.response.data?.message || "This mentor would go over capacity.";
        if (window.confirm(`${msg}\n\nAssign anyway?`)) {
          setBusy(false);
          return doAssign(studentIds, mentorId, true);
        }
      } else {
        flash(errorText(err, "Could not assign."));
      }
    } finally {
      setBusy(false);
    }
  };

  const doDecide = async (allocationIds, decision) => {
    setBusy(true);
    try {
      const data = await decideProposals({
        allocation_ids: allocationIds,
        decision,
      });
      flash(
        decision === "approve"
          ? `Approved ${data.count} proposal(s)`
          : `Rejected ${data.count} proposal(s) — the advisor will be asked to propose again`
      );
      await refresh();
    } catch (err) {
      flash(errorText(err, "Could not record that decision."));
    } finally {
      setBusy(false);
    }
  };

  const doRemove = async (row) => {
    if (
      !window.confirm(
        `Close ${row.student_name}'s allocation with ${row.mentor_name}?\n\n` +
          "The record is kept, not deleted."
      )
    )
      return;
    setBusy(true);
    try {
      await removeAllocation(row.allocation_id, {
        reason: "Allocation removed by the HOD",
      });
      flash(`Allocation closed for ${row.student_name} — the record is kept`);
      await refresh();
    } catch (err) {
      flash(errorText(err, "Could not remove."));
    } finally {
      setBusy(false);
    }
  };

  const showPreview = async () => {
    setBusy(true);
    try {
      const data = await getSplitPreview({ academic_year: academicYear });
      if (!data.total_students) {
        flash("Every student already has a mentor.");
        return;
      }
      setPreview(data);
    } catch (err) {
      flash(errorText(err, "Could not build the preview."));
    } finally {
      setBusy(false);
    }
  };

  const confirmSplit = async () => {
    setBusy(true);
    try {
      const data = await autoDistribute({ academic_year: academicYear });
      setPreview(null);
      flash(`Distributed ${data.assigned} students, balanced by grade band`);
      await refresh();
    } catch (err) {
      flash(errorText(err, "Could not distribute."));
    } finally {
      setBusy(false);
    }
  };

  const showWhy = async (studentId) => {
    if (why?.student_id === studentId) {
      setWhy(null);
      return;
    }
    try {
      const data = await getSuggestion(studentId, { academic_year: academicYear });
      setWhy({ ...data, student_id: studentId });
    } catch (err) {
      flash(errorText(err, "Could not fetch the suggestion."));
    }
  };

  // ================= RENDER HELPERS =================
  const setFilter = (key, value) =>
    setFilters((prev) => ({ ...prev, [key]: value }));

  const mentorLabel = (m) =>
    `${m.name} · ${m.assigned}/${m.capacity} · A ${m.band_a} B ${m.band_b} C ${m.band_c}` +
    (m.is_full ? " · FULL" : "");

  const balancePill = (state) =>
    state === "ok" ? "ma-green" : state === "warn" ? "ma-amber" : "ma-red";

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />

      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">
          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <h2 style={{ margin: 0 }}>Mentor Allocation</h2>
                {department && <span className="ma-pill ma-blue">{department}</span>}
              </div>
              <p>Approve class advisor proposals, assign and reassign student mentors</p>
            </div>

            <MentoringTabs />

            {error && (
              <div className="ma-note red" style={{ marginBottom: 16 }}>
                <b>Could not load</b>
                {error}
              </div>
            )}

            {/* ================= CONTEXT BAR ================= */}
            <div className="ma-context">
              <div>
                <span className="ma-label">Department</span>
                <div className="ma-static">{department || "—"}</div>
              </div>
              <div>
                <span className="ma-label">Academic Year</span>
                <select
                  value={academicYear}
                  onChange={(e) => setAcademicYear(e.target.value)}
                >
                  {(options?.academic_years || []).map((ay) => (
                    <option key={ay} value={ay}>
                      {prettyYear(ay)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="ma-spacer" />
              <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
                <span className="ma-pill ma-green">{counts.active} active</span>
                {counts.pending > 0 && (
                  <span className="ma-pill ma-amber">
                    {counts.pending} awaiting approval
                  </span>
                )}
                {counts.none > 0 && (
                  <span className="ma-pill ma-red">{counts.none} with no mentor</span>
                )}
              </div>
            </div>

            {/* ================= CARDS ================= */}
            <div className="ma-cards">
              <div className="ma-card">
                <div className="l">Total Mentors</div>
                <div className="n">{mentors.length}</div>
                <div className="d">{department}</div>
              </div>
              <div className="ma-card">
                <div className="l">Total Students</div>
                <div className="n">{counts.total}</div>
                <div className="d">
                  A {rows.filter((r) => r.grade_band === "A").length} · B{" "}
                  {rows.filter((r) => r.grade_band === "B").length} · C{" "}
                  {rows.filter((r) => r.grade_band === "C").length}
                </div>
              </div>
              <div className="ma-card">
                <div className="l">Active Allocations</div>
                <div className="n green">{counts.active}</div>
                <div className="d">
                  {counts.total
                    ? Math.round((counts.active / counts.total) * 100)
                    : 0}
                  % of students
                </div>
              </div>
              <div className="ma-card">
                <div className="l">Pending Allocations</div>
                <div className="n red">{counts.none}</div>
                <div className="d">
                  {counts.none ? "Need a mentor" : "Everyone has a mentor"}
                </div>
              </div>
            </div>

            {/* ================= TOOLBAR ================= */}
            <div className="ma-toolbar">
              <div className="ma-toggle">
                <button
                  className={view === "proposals" ? "on" : ""}
                  onClick={() => setView("proposals")}
                >
                  Review proposals
                </button>
                <button
                  className={view === "students" ? "on" : ""}
                  onClick={() => setView("students")}
                >
                  All students
                </button>
              </div>
              <div className="ma-spacer" style={{ flex: 1 }} />
              <button className="ma-btn" onClick={showPreview} disabled={busy}>
                Auto-distribute unassigned
              </button>
            </div>

            {loading && (
              <div className="ma-panel">
                <div className="ma-empty">Loading…</div>
              </div>
            )}

            {/* ================= PREVIEW ================= */}
            {!loading && preview && (
              <div className="ma-panel" style={{ border: "2px solid #2563eb" }}>
                <div className="ma-panel-head">
                  <div>
                    <h3>Preview — nothing is saved yet</h3>
                    <p>
                      {preview.total_students} students would go to{" "}
                      {preview.preview.length} mentor(s)
                    </p>
                  </div>
                  <div style={{ flex: 1 }} />
                  <span
                    className={`ma-pill ${
                      preview.any_over_capacity ? "ma-amber" : "ma-green"
                    }`}
                  >
                    {preview.any_over_capacity
                      ? "Some go over capacity"
                      : "All stay within capacity"}
                  </span>
                </div>
                <div className="ma-scroll">
                  <table className="ma-table">
                    <thead>
                      <tr>
                        <th>Mentor</th>
                        <th>Before</th>
                        <th></th>
                        <th>After</th>
                        <th>Adding</th>
                        <th>Capacity</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.preview.map((p) => (
                        <tr key={p.mentor_id}>
                          <td><b>{p.mentor_name}</b></td>
                          <td className="num">{p.before}</td>
                          <td style={{ color: "#9ca3af" }}>→</td>
                          <td className="num">
                            <b style={{ color: p.over_capacity ? "#dc2626" : "#1d4ed8" }}>
                              {p.after}
                            </b>
                          </td>
                          <td className="num">+{p.adding}</td>
                          <td>
                            <span
                              className={`ma-pill ${
                                p.over_capacity ? "ma-red" : "ma-green"
                              }`}
                            >
                              {p.after} / {p.capacity}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="ma-panel-foot">
                  <button className="ma-btn primary" onClick={confirmSplit} disabled={busy}>
                    Confirm split
                  </button>
                  <button className="ma-btn" onClick={() => setPreview(null)}>
                    Cancel
                  </button>
                  <div style={{ flex: 1 }} />
                  <span>Nothing is written until you confirm.</span>
                </div>
              </div>
            )}

            {/* ================= PROPOSALS VIEW ================= */}
            {!loading && view === "proposals" && (
              <>
                {batches.length === 0 && !pool?.count && (
                  <div className="ma-panel">
                    <div className="ma-empty">
                      <b style={{ display: "block", marginBottom: 6 }}>
                        Nothing waiting on you
                      </b>
                      Every advisor proposal has been decided and every student has a
                      mentor. Use <b>All students</b> to look someone up.
                    </div>
                  </div>
                )}

                {batches.map((b) => (
                  <div
                    key={b.key}
                    className={`ma-batch pending${openBatch[b.key] ? " open" : ""}`}
                  >
                    <div
                      className="ma-batch-head"
                      onClick={() =>
                        setOpenBatch((p) => ({ ...p, [b.key]: !p[b.key] }))
                      }
                    >
                      <div className="ma-avatar">
                        {(b.advisor_name || "?").slice(0, 2).toUpperCase()}
                      </div>
                      <div className="ma-batch-title">
                        <b>{b.advisor_name}</b>
                        <span>Proposed group list awaiting your approval</span>
                      </div>
                      <div className="ma-batch-count">
                        <b>{b.count}</b>
                        <span>students</span>
                      </div>
                      <div className="ma-chips">
                        {Object.entries(b.mentor_spread || {}).map(([name, n]) => (
                          <span className="ma-chip" key={name}>
                            {name} · {n}
                          </span>
                        ))}
                      </div>
                      <div className="ma-chips">
                        <span className={`ma-chip ${b.balanced ? "good" : "bad"}`}>
                          {b.balanced ? "✓" : "⚠"} A {b.band_a} B {b.band_b} C {b.band_c}
                        </span>
                      </div>
                      <div className="ma-batch-actions">
                        <button
                          className="ma-btn green"
                          disabled={busy}
                          onClick={(e) => {
                            e.stopPropagation();
                            doDecide(
                              b.students.map((s) => s.allocation_id),
                              "approve"
                            );
                          }}
                        >
                          Approve all
                        </button>
                        <button
                          className="ma-btn"
                          disabled={busy}
                          onClick={(e) => {
                            e.stopPropagation();
                            doDecide(
                              b.students.map((s) => s.allocation_id),
                              "reject"
                            );
                          }}
                        >
                          Reject all
                        </button>
                      </div>
                    </div>

                    {openBatch[b.key] && (
                      <div className="ma-batch-body">
                        {!b.balanced && (
                          <div style={{ padding: "12px 18px" }}>
                            <div className="ma-note amber">
                              <b>⚠ This proposal misses the composition rule</b>
                              A group should contain band A, B and C students. Approve
                              anyway if you know why, or reject and ask{" "}
                              {b.advisor_name} to redo it.
                            </div>
                          </div>
                        )}
                        <div className="ma-scroll">
                          <table className="ma-table">
                            <thead>
                              <tr>
                                <th>Student</th>
                                <th>Register No</th>
                                <th>Grade</th>
                                <th>Year</th>
                                <th>Proposed mentor</th>
                                <th></th>
                              </tr>
                            </thead>
                            <tbody>
                              {b.students.map((s) => (
                                <tr key={s.allocation_id}>
                                  <td><b>{s.student_name}</b></td>
                                  <td className="num">{s.roll_number}</td>
                                  <td>
                                    <span className={`ma-pill ${bandClass(s.grade_band)}`}>
                                      {s.grade_band || "—"}
                                    </span>
                                  </td>
                                  <td>{yearLabel(s.year)}</td>
                                  <td>{s.mentor_name}</td>
                                  <td className="ma-right">
                                    <div className="ma-actions">
                                      <button
                                        className="ma-btn small green"
                                        disabled={busy}
                                        onClick={() =>
                                          doDecide([s.allocation_id], "approve")
                                        }
                                      >
                                        Approve
                                      </button>
                                      <button
                                        className="ma-btn small danger"
                                        disabled={busy}
                                        onClick={() =>
                                          doDecide([s.allocation_id], "reject")
                                        }
                                      >
                                        Reject
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                ))}

                {pool?.count > 0 && (
                  <div className={`ma-batch pool${openBatch.pool ? " open" : ""}`}>
                    <div
                      className="ma-batch-head"
                      onClick={() => setOpenBatch((p) => ({ ...p, pool: !p.pool }))}
                    >
                      <div className="ma-avatar">⚠</div>
                      <div className="ma-batch-title">
                        <b>Students with no mentor</b>
                        <span>
                          Nobody has proposed anything for these — assign them or
                          auto-distribute
                        </span>
                      </div>
                      <div className="ma-batch-count">
                        <b>{pool.count}</b>
                        <span>students</span>
                      </div>
                      <div className="ma-chips">
                        <span className="ma-chip">A {pool.band_a}</span>
                        <span className="ma-chip">B {pool.band_b}</span>
                        <span className="ma-chip">C {pool.band_c}</span>
                      </div>
                      <div className="ma-batch-actions">
                        <button
                          className="ma-btn primary"
                          disabled={busy}
                          onClick={(e) => {
                            e.stopPropagation();
                            showPreview();
                          }}
                        >
                          Apply suggested split
                        </button>
                      </div>
                    </div>

                    {openBatch.pool && (
                      <div className="ma-batch-body ma-scroll">
                        <table className="ma-table">
                          <thead>
                            <tr>
                              <th>Student</th>
                              <th>Register No</th>
                              <th>Grade</th>
                              <th>CGPA</th>
                              <th>Year</th>
                              <th></th>
                            </tr>
                          </thead>
                          <tbody>
                            {pool.students.map((s) => (
                              <tr key={s.id}>
                                <td><b>{s.student_name}</b></td>
                                <td className="num">{s.roll_number}</td>
                                <td>
                                  <span className={`ma-pill ${bandClass(s.band)}`}>
                                    {s.band || "—"}
                                  </span>
                                </td>
                                <td className="num">
                                  {s.cgpa == null ? "—" : s.cgpa.toFixed(2)}
                                </td>
                                <td>{yearLabel(s.year)}</td>
                                <td className="ma-right">
                                  <button
                                    className="ma-btn small link"
                                    onClick={() => showWhy(s.id)}
                                  >
                                    Best fit?
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>

                        {why && (
                          <div style={{ padding: "0 18px 16px" }}>
                            <div className="ma-why">
                              <b>
                                Why {why.suggested?.name || "no one"}
                                {why.grade_band ? ` for a band ${why.grade_band} student?` : "?"}
                              </b>
                              <ul>
                                {(why.reasons || []).map((r, i) => (
                                  <li key={i}>{r}</li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}

            {/* ================= STUDENTS VIEW ================= */}
            {!loading && view === "students" && (
              <>
                <div className="ma-panel">
                  <div className="ma-panel-head">
                    <div><h3>Filter students</h3><p>All filters in one place</p></div>
                    <div style={{ flex: 1 }} />
                    <span className="ma-pill ma-blue">
                      Showing {rows.length}
                    </span>
                  </div>
                  <div className="ma-panel-body">
                    <div className="ma-filters">
                      <div>
                        <span className="ma-label">Year</span>
                        <select
                          value={filters.year}
                          onChange={(e) => setFilter("year", e.target.value)}
                        >
                          <option value="all">All years</option>
                          {(options?.years || []).map((y) => (
                            <option key={y} value={y}>{yearLabel(y)} Year</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <span className="ma-label">Course</span>
                        <select
                          value={filters.course}
                          onChange={(e) => setFilter("course", e.target.value)}
                        >
                          <option value="all">All courses</option>
                          {(options?.courses || []).map((c) => (
                            <option key={c.id} value={c.id}>{c.name}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <span className="ma-label">Grade</span>
                        <select
                          value={filters.band}
                          onChange={(e) => setFilter("band", e.target.value)}
                        >
                          <option value="all">All grades</option>
                          {(options?.bands || []).map((b) => (
                            <option key={b.value} value={b.value}>{b.label}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <span className="ma-label">Mentor</span>
                        <select
                          value={filters.mentor}
                          onChange={(e) => setFilter("mentor", e.target.value)}
                        >
                          <option value="all">All mentors</option>
                          <option value="none">Not assigned</option>
                          {mentors.map((m) => (
                            <option key={m.id} value={m.id}>{m.name}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <span className="ma-label">Status</span>
                        <select
                          value={filters.status}
                          onChange={(e) => setFilter("status", e.target.value)}
                        >
                          <option value="all">All</option>
                          {(options?.statuses || []).map((s) => (
                            <option key={s.value} value={s.value}>{s.label}</option>
                          ))}
                        </select>
                      </div>
                      <div className="ma-grow">
                        <span className="ma-label">Search</span>
                        <input
                          value={search}
                          placeholder="Student, register no, mentor name or employee ID"
                          onChange={(e) => setSearch(e.target.value)}
                        />
                      </div>
                      <button
                        className="ma-btn"
                        onClick={() => {
                          setFilters(EMPTY_FILTERS);
                          setSearch("");
                          setSelected({});
                        }}
                      >
                        Reset
                      </button>
                    </div>
                  </div>
                </div>

                <div className="ma-panel">
                  <div className="ma-panel-head">
                    <div><h3>All students</h3><p>{prettyYear(academicYear)}</p></div>
                  </div>

                  <div
                    className="ma-panel-body"
                    style={{ background: "#fbfcfd", borderBottom: "1px solid #f0f2f6" }}
                  >
                    <div className="ma-filters" style={{ alignItems: "center" }}>
                      <button className="ma-btn small" onClick={toggleAll}>
                        Select all in view
                      </button>
                      <span
                        className={`ma-pill ${
                          selectedIds.length ? "ma-blue" : "ma-grey"
                        }`}
                      >
                        {selectedIds.length
                          ? `${selectedIds.length} selected · A ${
                              selectedRows.filter((r) => r.grade_band === "A").length
                            } · B ${
                              selectedRows.filter((r) => r.grade_band === "B").length
                            } · C ${
                              selectedRows.filter((r) => r.grade_band === "C").length
                            }`
                          : "Nothing selected"}
                      </span>
                      <div style={{ flex: 1 }} />
                      <select
                        value={bulkMentor}
                        onChange={(e) => setBulkMentor(e.target.value)}
                        style={{ minWidth: 280 }}
                      >
                        <option value="">Assign to…</option>
                        {mentors.map((m) => (
                          <option key={m.id} value={m.id}>{mentorLabel(m)}</option>
                        ))}
                      </select>
                      <button
                        className="ma-btn primary"
                        disabled={busy}
                        onClick={() => doAssign(selectedIds, bulkMentor)}
                      >
                        Assign
                      </button>
                      <button className="ma-btn" onClick={() => setSelected({})}>
                        Clear
                      </button>
                    </div>
                  </div>

                  <div className="ma-scroll">
                    <table className="ma-table">
                      <thead>
                        <tr>
                          <th style={{ width: 34 }}></th>
                          <th>Student</th>
                          <th>Register No</th>
                          <th>Grade</th>
                          <th>CGPA</th>
                          <th>Year</th>
                          <th>Course</th>
                          <th>Academic Year</th>
                          <th>Mentor</th>
                          <th>Recommended By</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.length === 0 && (
                          <tr>
                            <td colSpan={12} className="ma-empty">
                              No student matches these filters.{" "}
                              <button
                                className="ma-btn link"
                                onClick={() => {
                                  setFilters(EMPTY_FILTERS);
                                  setSearch("");
                                }}
                              >
                                Clear filters
                              </button>
                            </td>
                          </tr>
                        )}

                        {rows.map((r) => {
                          const st = statusPill(r.status);
                          return (
                            <tr key={r.student_id}>
                              <td>
                                <span
                                  className={`ma-check${
                                    selected[r.student_id] ? " on" : ""
                                  }`}
                                  onClick={() => toggleOne(r.student_id)}
                                >
                                  ✓
                                </span>
                              </td>
                              <td><b>{r.student_name}</b></td>
                              <td className="num">{r.roll_number}</td>
                              <td>
                                <span className={`ma-pill ${bandClass(r.grade_band)}`}>
                                  {r.grade_band || "—"}
                                </span>
                              </td>
                              <td className="num">
                                {r.cgpa == null ? "—" : r.cgpa.toFixed(2)}
                              </td>
                              <td>{yearLabel(r.year)}</td>
                              <td>{r.course_name || "—"}</td>
                              <td className="num">{prettyYear(r.academic_year)}</td>
                              <td>
                                {r.mentor_name || (
                                  <span className="ma-pill ma-red">Not assigned</span>
                                )}
                              </td>
                              <td style={{ fontSize: 12, color: "#6b7280" }}>
                                {r.recommended_by || "—"}
                              </td>
                              <td>
                                <span className={`ma-pill ${st.cls}`}>{st.label}</span>
                              </td>
                              <td className="ma-right">
                                <div className="ma-actions">
                                  {r.status === "pending" && (
                                    <>
                                      <button
                                        className="ma-btn small green"
                                        disabled={busy}
                                        onClick={() =>
                                          doDecide([r.allocation_id], "approve")
                                        }
                                      >
                                        Approve
                                      </button>
                                      <button
                                        className="ma-btn small danger"
                                        disabled={busy}
                                        onClick={() =>
                                          doDecide([r.allocation_id], "reject")
                                        }
                                      >
                                        Reject
                                      </button>
                                    </>
                                  )}
                                  {r.status === "active" && (
                                    <>
                                      <button
                                        className="ma-btn small violet"
                                        onClick={() => {
                                          setSelected({ [r.student_id]: true });
                                          flash("Selected — pick a mentor in the bar above");
                                        }}
                                      >
                                        Reassign
                                      </button>
                                      <button
                                        className="ma-btn small danger"
                                        disabled={busy}
                                        onClick={() => doRemove(r)}
                                      >
                                        Remove
                                      </button>
                                    </>
                                  )}
                                  {r.status === "none" && (
                                    <button
                                      className="ma-btn small primary"
                                      onClick={() => {
                                        setSelected({ [r.student_id]: true });
                                        showWhy(r.student_id);
                                      }}
                                    >
                                      Assign
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {why && view === "students" && (
                    <div className="ma-panel-body">
                      <div className="ma-why">
                        <b>Suggested: {why.suggested?.name || "no one available"}</b>
                        <ul>
                          {(why.reasons || []).map((r, i) => (
                            <li key={i}>{r}</li>
                          ))}
                        </ul>
                        {why.suggested && (
                          <button
                            className="ma-btn small primary"
                            style={{ marginTop: 10 }}
                            onClick={() =>
                              doAssign([why.student_id], why.suggested.id)
                            }
                          >
                            Assign to {why.suggested.name}
                          </button>
                        )}
                      </div>
                    </div>
                  )}

                  <div className="ma-panel-foot">
                    Remove closes an allocation and keeps the record. Reassign opens a
                    new one. Neither deletes history.
                  </div>
                </div>
              </>
            )}

            {/* ================= MENTOR CAPACITY ================= */}
            {!loading && mentors.length > 0 && (
              <div className="ma-panel">
                <div className="ma-panel-head">
                  <div>
                    <h3>Mentor capacity</h3>
                    <p>Assigned, capacity and how many places are left</p>
                  </div>
                  <div style={{ flex: 1 }} />
                  <span
                    className={`ma-pill ${
                      mentors.some((m) => m.balance_state !== "ok")
                        ? "ma-amber"
                        : "ma-green"
                    }`}
                  >
                    {mentors.filter((m) => m.balance_state !== "ok").length
                      ? `${
                          mentors.filter((m) => m.balance_state !== "ok").length
                        } need attention`
                      : "All balanced"}
                  </span>
                </div>
                <div className="ma-panel-body">
                  <div className="ma-capacity">
                    {mentors.map((m) => {
                      const pct = Math.min(100, (m.assigned / m.capacity) * 100);
                      const barClass = m.is_full
                        ? "red"
                        : m.available <= 3
                        ? "amber"
                        : "green";
                      return (
                        <div
                          className="ma-cap"
                          key={m.id}
                          onClick={() => setBulkMentor(String(m.id))}
                          title="Click to pick this mentor in the assign bar"
                        >
                          <div className="name">{m.name}</div>
                          <div className="big">
                            <b>{m.assigned}</b>
                            <span>of {m.capacity}</span>
                            <div style={{ flex: 1 }} />
                            <span
                              className={`ma-pill ${
                                m.is_full
                                  ? "ma-red"
                                  : m.available <= 3
                                  ? "ma-amber"
                                  : "ma-green"
                              }`}
                            >
                              {m.is_full ? "Full" : `${m.available} free`}
                            </span>
                          </div>
                          <div className="ma-bar">
                            <i className={barClass} style={{ width: `${pct}%` }} />
                          </div>
                          <div className="ma-mix">
                            <i style={{ background: "#10b981", flex: m.band_a || 0.02 }} />
                            <i style={{ background: "#2563eb", flex: m.band_b || 0.02 }} />
                            <i style={{ background: "#f59e0b", flex: m.band_c || 0.02 }} />
                          </div>
                          <div className="ma-small">
                            A {m.band_a} · B {m.band_b} · C {m.band_c}
                          </div>
                          <div style={{ marginTop: 7 }}>
                            <span className={`ma-pill ${balancePill(m.balance_state)}`}>
                              {m.balance_message}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

          </div>
        </div>
      </div>

      {toast && <div className="ma-toast">{toast}</div>}
    </div>
  );
}