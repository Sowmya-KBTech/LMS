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

  // capacity is reference material, not the task. Closed until asked for.
  const [showCapacity, setShowCapacity] = useState(false);

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

  const loadAll = useCallback(async (ay, f) => {
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
  }, []);

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

  const proposalStudents = useMemo(
    () => batches.reduce((n, b) => n + (b.count || 0), 0),
    [batches]
  );

  const selectedIds = useMemo(
    () => Object.keys(selected).filter((k) => selected[k]).map(Number),
    [selected]
  );

  const selectedRows = useMemo(
    () => rows.filter((r) => selected[r.student_id]),
    [rows, selected]
  );

  const toggleOne = (id) => setSelected((prev) => ({ ...prev, [id]: !prev[id] }));

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
          : `Returned ${data.count} proposal(s) — the class in-charge will be asked to propose again`
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
  const setFilter = (key, value) => setFilters((prev) => ({ ...prev, [key]: value }));

  const mentorLabel = (m) =>
    `${m.name} · ${m.assigned}/${m.capacity} · A ${m.band_a} B ${m.band_b} C ${m.band_c}` +
    (m.is_full ? " · FULL" : "");

  const balancePill = (state) =>
    state === "ok" ? "ma-green" : state === "warn" ? "ma-amber" : "ma-red";

  const needAttention = mentors.filter((m) => m.balance_state !== "ok").length;

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />

      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">
          <div className="content">

            {/* ================= HEADER =================
                Department, year and title in one row. The counts that used to
                sit here are now in one place only, the summary strip below. */}
            <div className="header-box">
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <h2 style={{ margin: 0 }}>Mentor Allocation</h2>
                {department && <span className="ma-pill ma-blue">{department}</span>}
                <div style={{ flex: 1 }} />
                <select
                  value={academicYear}
                  onChange={(e) => setAcademicYear(e.target.value)}
                  style={{ minWidth: 150 }}
                >
                  {(options?.academic_years || []).map((ay) => (
                    <option key={ay} value={ay}>
                      {prettyYear(ay)}
                    </option>
                  ))}
                </select>
              </div>
              <p>
                Every student gets a faculty mentor. Class in-charges propose groups, you
                approve them, and anyone left over you assign yourself.
              </p>
            </div>

            <MentoringTabs />

            {error && (
              <div className="ma-note red" style={{ marginBottom: 16 }}>
                <b>Could not load</b>
                {error}
              </div>
            )}

            {/* ================= WHAT NEEDS DOING =================
                One banner, one primary action. Previously the same job was
                offered by two differently-named buttons in two places, both
                calling the same function. */}
            {!loading && !preview && (
              <>
                {proposalStudents > 0 && (
                  <div className="ma-note amber" style={{ marginBottom: 14 }}>
                    <b>
                      {batches.length} class in-charge proposal
                      {batches.length === 1 ? "" : "s"} waiting on you
                      {" · "}
                      {proposalStudents} student{proposalStudents === 1 ? "" : "s"}
                    </b>
                    Open a proposal below to see the students and the mentor the
                    class in-charge picked, then approve or send it back.
                  </div>
                )}

                {counts.none > 0 && (
                  <div className="ma-note blue" style={{ marginBottom: 14 }}>
                    <b>
                      {counts.none} student{counts.none === 1 ? "" : "s"} have no
                      mentor
                    </b>
                    <div style={{ marginTop: 8, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                      <button className="ma-btn primary" onClick={showPreview} disabled={busy}>
                        Suggest a balanced split
                      </button>
                      <span style={{ fontSize: 14, color: "#5D5A6B" }}>
                        Shows you the plan first. Nothing is saved until you confirm.
                      </span>
                    </div>
                  </div>
                )}

                {proposalStudents === 0 && counts.none === 0 && counts.total > 0 && (
                  <div className="ma-note" style={{ marginBottom: 14 }}>
                    <b>Nothing waiting on you</b>
                    Every student in {department} has a mentor and no proposal is
                    pending. Use <b>All students</b> to look someone up or make a
                    change.
                  </div>
                )}
              </>
            )}

            {/* ================= SUMMARY =================
                Four figures, each named for what it actually counts. The old
                red card was labelled "Pending Allocations" but rendered the
                no-mentor count, so two different things shared one name. */}
            <div className="ma-cards">
              <div className="ma-card">
                <div className="l">Students</div>
                <div className="n">{counts.total}</div>
                <div className="d">
                  Grade A {rows.filter((r) => r.grade_band === "A").length} · B{" "}
                  {rows.filter((r) => r.grade_band === "B").length} · C{" "}
                  {rows.filter((r) => r.grade_band === "C").length}
                </div>
              </div>
              <div className="ma-card">
                <div className="l">Have a mentor</div>
                <div className="n green">{counts.active}</div>
                <div className="d">
                  {counts.total ? Math.round((counts.active / counts.total) * 100) : 0}% of
                  students
                </div>
              </div>
              <div className="ma-card">
                <div className="l">Awaiting your approval</div>
                <div className="n">{counts.pending}</div>
                <div className="d">
                  {counts.pending ? "Proposed by a class in-charge" : "No proposal pending"}
                </div>
              </div>
              <div className="ma-card">
                <div className="l">No mentor yet</div>
                <div className={counts.none ? "n red" : "n"}>{counts.none}</div>
                <div className="d">
                  {counts.none ? "Nobody has proposed these" : "Everyone is allocated"}
                </div>
              </div>
            </div>

            {/* ================= VIEW SWITCH ================= */}
            <div className="ma-toolbar">
              <div className="ma-toggle">
                <button
                  className={view === "proposals" ? "on" : ""}
                  onClick={() => setView("proposals")}
                >
                  Needs a decision
                  {proposalStudents + (pool?.count || 0) > 0
                    ? ` (${batches.length + (pool?.count ? 1 : 0)})`
                    : ""}
                </button>
                <button
                  className={view === "students" ? "on" : ""}
                  onClick={() => setView("students")}
                >
                  All students
                </button>
              </div>
              <div className="ma-spacer" style={{ flex: 1 }} />
            </div>

            {loading && (
              <div className="ma-panel">
                <div className="ma-empty">Loading…</div>
              </div>
            )}

            {/* ================= PREVIEW ================= */}
            {!loading && preview && (
              <div className="ma-panel" style={{ border: "2px solid #4B32C3" }}>
                <div className="ma-panel-head">
                  <div>
                    <h3>Suggested split — nothing is saved yet</h3>
                    <p>
                      {preview.total_students} student
                      {preview.total_students === 1 ? "" : "s"} would go to{" "}
                      {preview.preview.length} mentor
                      {preview.preview.length === 1 ? "" : "s"}, balanced so each
                      mentor gets a mix of grade bands
                    </p>
                  </div>
                  <div style={{ flex: 1 }} />
                  <span
                    className={`ma-pill ${preview.any_over_capacity ? "ma-amber" : "ma-green"}`}
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
                        <th>Has now</th>
                        <th></th>
                        <th>Would have</th>
                        <th>Adding</th>
                        <th>Against capacity</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.preview.map((p) => (
                        <tr key={p.mentor_id}>
                          <td>
                            <b>{p.mentor_name}</b>
                          </td>
                          <td className="num">{p.before}</td>
                          <td style={{ color: "#85839A" }}>→</td>
                          <td className="num">
                            <b style={{ color: p.over_capacity ? "#dc2626" : "#4B32C3" }}>
                              {p.after}
                            </b>
                          </td>
                          <td className="num">+{p.adding}</td>
                          <td>
                            <span
                              className={`ma-pill ${p.over_capacity ? "ma-red" : "ma-green"}`}
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
                    Confirm and assign
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
                      Every class in-charge proposal has been decided and every student has a
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
                      onClick={() => setOpenBatch((p) => ({ ...p, [b.key]: !p[b.key] }))}
                    >
                      <div className="ma-avatar">
                        {(b.advisor_name || "?").slice(0, 2).toUpperCase()}
                      </div>
                      <div className="ma-batch-title">
                        <b>{b.advisor_name}</b>
                        <span>
                          {openBatch[b.key]
                            ? "Click to collapse"
                            : "Click to see the students and their proposed mentors"}
                        </span>
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
                        <span
                          className={`ma-chip ${b.balanced ? "good" : "bad"}`}
                          title={
                            b.balanced
                              ? "This group mixes grade bands as the rule requires"
                              : "This group is missing a grade band"
                          }
                        >
                          {b.balanced ? "✓ Mixed grades" : "⚠ Grade gap"} · A {b.band_a} B{" "}
                          {b.band_b} C {b.band_c}
                        </span>
                      </div>
                      <div className="ma-batch-actions">
                        <button
                          className="ma-btn green"
                          disabled={busy}
                          onClick={(e) => {
                            e.stopPropagation();
                            doDecide(b.students.map((s) => s.allocation_id), "approve");
                          }}
                        >
                          Approve all
                        </button>
                        <button
                          className="ma-btn"
                          disabled={busy}
                          onClick={(e) => {
                            e.stopPropagation();
                            doDecide(b.students.map((s) => s.allocation_id), "reject");
                          }}
                        >
                          Send back
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
                              anyway if you know why, or send it back and ask{" "}
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
                                  <td>
                                    <b>{s.student_name}</b>
                                  </td>
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
                                        onClick={() => doDecide([s.allocation_id], "approve")}
                                      >
                                        Approve
                                      </button>
                                      <button
                                        className="ma-btn small danger"
                                        disabled={busy}
                                        onClick={() => doDecide([s.allocation_id], "reject")}
                                      >
                                        Send back
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
                          No class in-charge has proposed anything for these. Use the suggested
                          split above, or assign them one at a time under All students.
                        </span>
                      </div>
                      <div className="ma-batch-count">
                        <b>{pool.count}</b>
                        <span>students</span>
                      </div>
                      <div className="ma-chips">
                        <span className="ma-chip">Grade A {pool.band_a}</span>
                        <span className="ma-chip">B {pool.band_b}</span>
                        <span className="ma-chip">C {pool.band_c}</span>
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
                                <td>
                                  <b>{s.student_name}</b>
                                </td>
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
                                    Who fits best?
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
                                {why.grade_band
                                  ? ` for a grade ${why.grade_band} student?`
                                  : "?"}
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
                    <div>
                      <h3>Find a student</h3>
                      <p>Narrow the list, then assign or reassign below</p>
                    </div>
                    <div style={{ flex: 1 }} />
                    <span className="ma-pill ma-blue">Showing {rows.length}</span>
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
                            <option key={y} value={y}>
                              {yearLabel(y)} Year
                            </option>
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
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
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
                            <option key={b.value} value={b.value}>
                              {b.label}
                            </option>
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
                            <option key={m.id} value={m.id}>
                              {m.name}
                            </option>
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
                            <option key={s.value} value={s.value}>
                              {s.label}
                            </option>
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
                    <div>
                      <h3>All students</h3>
                      <p>{prettyYear(academicYear)}</p>
                    </div>
                  </div>

                  {/* assign bar — only useful once something is ticked, so it
                      says so rather than sitting there looking broken */}
                  <div
                    className="ma-panel-body"
                    style={{ background: "#fbfcfd", borderBottom: "1px solid #ECECF0" }}
                  >
                    <div className="ma-filters" style={{ alignItems: "center" }}>
                      <button className="ma-btn small" onClick={toggleAll}>
                        Select all in view
                      </button>
                      <span
                        className={`ma-pill ${selectedIds.length ? "ma-blue" : "ma-grey"}`}
                      >
                        {selectedIds.length
                          ? `${selectedIds.length} selected · A ${
                              selectedRows.filter((r) => r.grade_band === "A").length
                            } · B ${
                              selectedRows.filter((r) => r.grade_band === "B").length
                            } · C ${
                              selectedRows.filter((r) => r.grade_band === "C").length
                            }`
                          : "Tick students to assign them"}
                      </span>
                      <div style={{ flex: 1 }} />
                      <select
                        value={bulkMentor}
                        onChange={(e) => setBulkMentor(e.target.value)}
                        style={{ minWidth: 280 }}
                      >
                        <option value="">Choose a mentor…</option>
                        {mentors.map((m) => (
                          <option key={m.id} value={m.id}>
                            {mentorLabel(m)}
                          </option>
                        ))}
                      </select>
                      <button
                        className="ma-btn primary"
                        disabled={busy || !selectedIds.length || !bulkMentor}
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
                          <th>Mentor</th>
                          <th>Proposed by</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.length === 0 && (
                          <tr>
                            <td colSpan={11} className="ma-empty">
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
                                  className={`ma-check${selected[r.student_id] ? " on" : ""}`}
                                  onClick={() => toggleOne(r.student_id)}
                                >
                                  ✓
                                </span>
                              </td>
                              <td>
                                <b>{r.student_name}</b>
                              </td>
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
                              <td>
                                {r.mentor_name || (
                                  <span className="ma-pill ma-red">Not assigned</span>
                                )}
                              </td>
                              <td style={{ fontSize: 13, color: "#5D5A6B" }}>
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
                                        onClick={() => doDecide([r.allocation_id], "approve")}
                                      >
                                        Approve
                                      </button>
                                      <button
                                        className="ma-btn small danger"
                                        disabled={busy}
                                        onClick={() => doDecide([r.allocation_id], "reject")}
                                      >
                                        Send back
                                      </button>
                                    </>
                                  )}
                                  {r.status === "active" && (
                                    <>
                                      <button
                                        className="ma-btn small violet"
                                        onClick={() => {
                                          setSelected({ [r.student_id]: true });
                                          flash("Selected — now pick a mentor in the bar above");
                                        }}
                                      >
                                        Change mentor
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
                        <b>Best fit: {why.suggested?.name || "no one available"}</b>
                        <ul>
                          {(why.reasons || []).map((r, i) => (
                            <li key={i}>{r}</li>
                          ))}
                        </ul>
                        {why.suggested && (
                          <button
                            className="ma-btn small primary"
                            style={{ marginTop: 10 }}
                            onClick={() => doAssign([why.student_id], why.suggested.id)}
                          >
                            Assign to {why.suggested.name}
                          </button>
                        )}
                      </div>
                    </div>
                  )}

                  <div className="ma-panel-foot">
                    Remove closes an allocation and keeps the record. Change mentor opens
                    a new one. Neither deletes history.
                  </div>
                </div>
              </>
            )}

            {/* ================= MENTOR CAPACITY =================
                Reference, not a task. Collapsed by default so it stops taking
                half the screen while empty. */}
            {!loading && mentors.length > 0 && (
              <div className="ma-panel">
                <div
                  className="ma-panel-head"
                  style={{ cursor: "pointer" }}
                  onClick={() => setShowCapacity((v) => !v)}
                >
                  <div>
                    <h3>How loaded is each mentor?</h3>
                    <p>
                      {mentors.length} mentor{mentors.length === 1 ? "" : "s"} in{" "}
                      {department}
                      {needAttention
                        ? ` · ${needAttention} could do with a better grade mix`
                        : " · all have a balanced grade mix"}
                    </p>
                  </div>
                  <div style={{ flex: 1 }} />
                  <button className="ma-btn small">
                    {showCapacity ? "Hide" : "Show"}
                  </button>
                </div>

                {showCapacity && (
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
                            onClick={() => {
                              setBulkMentor(String(m.id));
                              setView("students");
                              flash(`${m.name} selected in the assign bar`);
                            }}
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

                            <div className="ma-small" style={{ marginBottom: 3 }}>
                              How full
                            </div>
                            <div className="ma-bar">
                              <i className={barClass} style={{ width: `${pct}%` }} />
                            </div>

                            <div className="ma-small" style={{ marginTop: 7, marginBottom: 3 }}>
                              Grade mix · A {m.band_a} · B {m.band_b} · C {m.band_c}
                            </div>
                            <div className="ma-mix">
                              <i style={{ background: "#10b981", flex: m.band_a || 0.02 }} />
                              <i style={{ background: "#4B32C3", flex: m.band_b || 0.02 }} />
                              <i style={{ background: "#f59e0b", flex: m.band_c || 0.02 }} />
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
                )}
              </div>
            )}

          </div>
        </div>
      </div>

      {toast && <div className="ma-toast">{toast}</div>}
    </div>
  );
}