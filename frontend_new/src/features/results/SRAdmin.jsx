import { useEffect, useMemo, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../styles/Attendance.css";
import "../../styles/Credits.css";
import ImportExport from "../../components/ImportExport";
import { previewGrade } from "./creditsUtil";

// Grades with NO regulation set up (old fixed bands) - preview only; the
// backend recomputes on save. WAVE 3 PART 1B: with a regulation, each student
// is previewed with their own regulation's rule (results/entry-rules/) and
// marks are entered as internal + end-semester.
const GRADE_BANDS = [
  [90, "O"], [80, "A+"], [70, "A"], [60, "B+"], [50, "B"], [40, "C"], [0, "F"],
];
const PASS_PERCENT = 40;
const legacyGrade = (scored, max) => {
  if (scored === "" || scored == null || !max) return null;
  const pct = (Number(scored) / Number(max)) * 100;
  const band = GRADE_BANDS.find(([t]) => pct >= t);
  return { grade: band[1], pass: pct >= PASS_PERCENT };
};
const blankRow = { internal: "", end: "", total: "", hand: "" };
const val = (v) => (v === null || v === undefined ? "" : String(v));

export default function SRAdmin({ embedded = false }) {
  const [open, setOpen] = useState(false);

  const [subjects, setSubjects] = useState([]);   // all teaching assignments
  const [selectedCourse, setSelectedCourse] = useState("");
  const [selectedYear, setSelectedYear]     = useState("");
  const [selectedTA, setSelectedTA] = useState("");   // teaching assignment (for subject id + course/year/sem)
  const [maxMarks, setMaxMarks]     = useState(100);
  const [mode, setMode]             = useState("regular");   // WAVE 3: "regular" | "arrear" (re-exam)
  const [examSession, setExamSession] = useState("");

  const [students, setStudents] = useState([]);
  const [rows, setRows]         = useState({});   // { studentId: {internal, end, total, hand} }
  const [rules, setRules]       = useState({ rules: {}, students: {} });
  const [rowErrors, setRowErrors] = useState({});  // { studentId: message } from the server
  // students whose SAVED entry has no marks = absent
  const [absentSaved, setAbsentSaved] = useState({});
  const [loading, setLoading]   = useState(false);
  const [saving, setSaving]     = useState(false);
  const [notice, setNotice]     = useState(null);  // { tone, text }
  const [publishing, setPublishing] = useState(false);

  // ── all teaching assignments ──
  useEffect(() => {
    API.get("/teaching-assignments/").then((res) => {
      setSubjects(res.data?.results || res.data || []);
    });
  }, []);

  // ── cascade lists ──
  const courses = [...new Set(subjects.map((s) => s.course_name))].sort();
  const years = selectedCourse
    ? [...new Set(subjects.filter((s) => s.course_name === selectedCourse).map((s) => s.year_number))].sort((a, b) => a - b)
    : [];
  const filteredSubjects = subjects.filter((s) =>
    (!selectedCourse || s.course_name === selectedCourse) &&
    (!selectedYear || String(s.year_number) === String(selectedYear))
  );

  // the chosen assignment object (gives us subject id + course/year/semester)
  const chosenTA = subjects.find((s) => String(s.id) === String(selectedTA));

  const ruleOf = (sid) => rules.rules[String(rules.students[String(sid)])] || null;
  const split = useMemo(() => Object.values(rules.students).some((r) => r != null), [rules]);
  const handGrades = useMemo(() => [...new Set(Object.values(rules.rules).flatMap((r) => r.hand_grades || []))], [rules]);
  const anyRule = Object.values(rules.rules)[0];

  // ── roster + existing marks (regular), or students with an arrear (re-exam) ──
  const loadRoster = async (keepNotice = false) => {
    if (!chosenTA) return;
    setLoading(true);
    if (!keepNotice) setNotice(null);
    setRowErrors({});
    try {
      let roster = [];
      const init = {};
      const absent = {};
      if (mode === "arrear") {
        const res = await API.get(`results/arrear-roster/?subject=${chosenTA.subject}`);
        roster = res.data.students || [];
        roster.forEach((e) => { init[e.student] = { ...blankRow, internal: val(e.internal_marks) }; });
      } else {
        const [stuRes, srRes] = await Promise.all([
          API.get(`/exam-students/?course=${chosenTA.course}&year=${chosenTA.year_number}&semester=${chosenTA.semester}`),
          API.get(`/semester-results/?semester=${chosenTA.semester}`),
        ]);
        roster = stuRes.data?.results || stuRes.data || [];
        roster.forEach((e) => { init[e.student] = { ...blankRow }; });
        (srRes.data?.results || srRes.data || []).forEach((res) => {
          const entry = (res.entries || []).find((en) => en.subject === chosenTA.subject || en.subject_name === chosenTA.subject_name);
          if (!entry || !(res.student in init)) return;
          const hand = ["arrear", "excluded"].includes(entry.outcome) ? entry.grade : "";
          if (entry.internal_marks != null) {
            init[res.student] = { ...blankRow, internal: val(entry.internal_marks), end: val(entry.end_marks), hand };
          } else if (entry.marks_obtained != null) {
            init[res.student] = { ...blankRow, total: val(entry.marks_obtained), hand };
            if (entry.max_marks) setMaxMarks(entry.max_marks);
          } else {
            init[res.student] = { ...blankRow, hand };
            if (!hand) absent[res.student] = true;
          }
        });
      }
      setStudents(roster);
      setRows(init);
      setAbsentSaved(absent);
      if (roster.length) {
        const ids = roster.map((e) => e.student).join(",");
        const r = await API.get(`results/entry-rules/?subject=${chosenTA.subject}&ids=${ids}`);
        setRules({ rules: r.data.rules || {}, students: r.data.students || {} });
      } else {
        setRules({ rules: {}, students: {} });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedTA || !chosenTA) { setStudents([]); setRows({}); return; }
    loadRoster();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTA, mode]);

  const setCell = (studentId, key, value) => {
    setRows((prev) => ({ ...prev, [studentId]: { ...(prev[studentId] || blankRow), [key]: value } }));
    setRowErrors((prev) => ({ ...prev, [studentId]: undefined }));
  };

  const saveResults = async () => {
    if (!selectedTA || !chosenTA) return;
    if (mode === "arrear" && !examSession.trim()) {
      setNotice({ tone: "bad", text: "Give the exam session of this re-exam, like Apr/May 2026." });
      return;
    }
    setSaving(true);
    setNotice(null);
    // a re-exam lists every student with an arrear: only those with marks or a grade typed are saved
    const typed = (r) => r.end !== "" || r.total !== "" || r.hand;
    const list = mode === "arrear" ? students.filter((e) => typed(rows[e.student] || blankRow)) : students;
    if (!list.length) {
      setSaving(false);
      setNotice({ tone: "bad", text: "Type the re-exam marks for at least one student." });
      return;
    }
    const records = list.map((e) => {
      const r = rows[e.student] || blankRow;
      const rec = { student: e.student };
      if (r.hand) rec.grade = r.hand;
      else if (ruleOf(e.student) && (r.internal !== "" || r.end !== "")) {
        rec.internal_marks = r.internal === "" ? null : Number(r.internal);
        rec.end_marks = r.end === "" ? null : Number(r.end);
      } else rec.marks_obtained = r.total === "" ? null : Number(r.total);
      return rec;
    });
    try {
      const res = await API.post("/semester-results/save_results/", {
        subject: chosenTA.subject,          // subject id from the assignment
        semester: chosenTA.semester,
        max_marks: maxMarks,
        exam_session: examSession.trim(),
        records,
      });
      const d = res.data || {};
      setNotice({ tone: "ok", text: d.new_attempt ? `Saved. ${d.new_attempt} re-exam attempt${d.new_attempt === 1 ? "" : "s"} recorded.` : "Marks saved." });
      setRowErrors({});
      if (mode === "arrear") loadRoster(true);
    } catch (err) {
      const d = err.response?.data;
      const map = {};
      (d?.errors || []).forEach((x) => { map[x.student] = x.detail; });
      setRowErrors(map);
      setNotice({ tone: "bad", text: d?.detail || "Error saving results. Please try again." });
    } finally {
      setSaving(false);
    }
  };

  // publish every result for this semester
  const publishSemester = async () => {
    if (!chosenTA) return;
    if (!window.confirm(`Publish all Semester ${chosenTA.semester} results to students?`)) return;
    setPublishing(true);
    try {
      const res = await API.get(`/semester-results/?semester=${chosenTA.semester}`);
      const results = res.data?.results || res.data || [];
      await Promise.all(
        results.map((r) => API.post(`/semester-results/${r.id}/publish/`))
      );
      setNotice({ tone: "ok", text: `Semester ${chosenTA.semester} results published.` });
    } catch (err) {
      setNotice({ tone: "bad", text: err.response?.data?.detail || "Error publishing. Please try again." });
    } finally {
      setPublishing(false);
    }
  };

  const preview = (sid) => {
    const r = rows[sid] || blankRow;
    const rule = ruleOf(sid);
    if (rule) return previewGrade(rule, { internal: r.internal, end: r.end, total: r.total, maxMarks, hand: r.hand });
    if (absentSaved[sid] && r.total === "") return { grade: "F", pass: false, note: "absent" };
    return legacyGrade(r.total, maxMarks);
  };

  const numInput = (sid, key, max, label) => (
    <input className="att-input" type="number" min={0} max={max} aria-label={label}
      style={{ width: 76, textAlign: "center" }} value={(rows[sid] || blankRow)[key]}
      disabled={!!(rows[sid] || blankRow).hand}
      onChange={(ev) => setCell(sid, key, ev.target.value)} />
  );

  const body = (
    <>
      <div className="att-header">
        <div>
          <h1 className="att-title">Semester Result</h1>
          <p className="att-subtitle">Enter final marks and publish to students</p>
        </div>
      </div>

      <div className="att-card">
        <h2 className="att-card-title">Enter Marks</h2>

        {/* Course → Year → Subject cascade */}
        <div className="att-filter-grid">
          <div className="att-field">
            <label className="att-label">Course</label>
            <select className="att-input" value={selectedCourse}
              onChange={(e) => { setSelectedCourse(e.target.value); setSelectedYear(""); setSelectedTA(""); }}>
              <option value="">— All Courses —</option>
              {courses.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="att-field">
            <label className="att-label">Year</label>
            <select className="att-input" value={selectedYear}
              onChange={(e) => { setSelectedYear(e.target.value); setSelectedTA(""); }}
              disabled={!selectedCourse}>
              <option value="">— All Years —</option>
              {years.map((y) => <option key={y} value={y}>Year {y}</option>)}
            </select>
          </div>
          <div className="att-field">
            <label className="att-label">Subject</label>
            <select className="att-input" value={selectedTA}
              onChange={(e) => setSelectedTA(e.target.value)}>
              <option value="">— Select Subject —</option>
              {filteredSubjects.map((s) => (
                <option key={s.id} value={s.id}>{s.subject_name} (Sem {s.semester})</option>
              ))}
            </select>
          </div>
          {/* WAVE 3 PART 1B: regular exam or an arrear re-exam, and its exam session */}
          <div className="att-field">
            <label className="att-label">Students</label>
            <select className="att-input" value={mode} onChange={(e) => setMode(e.target.value)} disabled={!selectedTA}>
              <option value="regular">This semester's class</option>
              <option value="arrear">Arrear re-exam</option>
            </select>
          </div>
          <div className="att-field">
            <label className="att-label">Exam session{mode === "arrear" ? " *" : ""}</label>
            <input className="att-input" value={examSession} maxLength={30} placeholder="e.g. Nov/Dec 2026"
              onChange={(e) => setExamSession(e.target.value)} />
          </div>
        </div>

        {/* Import / Export (shared engine) — once a subject is chosen */}
        {selectedTA && mode === "regular" && (
          <div className="kb-io-bar">
            <ImportExport
              importer="results"
              label="results"
              matchLabel="roll number"
              modes={["upsert"]}
              options={{ teaching_assignment: selectedTA, max_marks: maxMarks }}
              note={split
                ? "Fill Internal and End-sem (or Marks for a total). AB = absent · Grade by hand = SA / W · blank = unchanged. Published results can't be changed."
                : `Marks out of ${maxMarks} · AB = absent · blank = unchanged. Grades are worked out automatically; published results can't be changed.`}
              onDone={() => loadRoster()}
            />
          </div>
        )}

        {notice && <div className={`cr-notice ${notice.tone}`} role={notice.tone === "ok" ? "status" : "alert"}>{notice.text}</div>}

        {loading ? (
          <div className="att-state"><div className="att-spinner" /><p>Loading students…</p></div>
        ) : !selectedTA ? (
          <div className="att-state"><p>Select a subject above to enter final marks.</p></div>
        ) : students.length === 0 ? (
          <div className="att-state"><p>{mode === "arrear" ? "No student has an arrear in this subject." : "No students found for this course, year and semester."}</p></div>
        ) : (
          <>
            {split && anyRule && (
              <p className="cr-muted" style={{ margin: "0 0 10px" }}>
                Regulation {anyRule.regulation} · {anyRule.kind}: internal {anyRule.internal_max} + end-sem {anyRule.end_max};
                pass needs end-sem {anyRule.min_end_pct}% and total {anyRule.min_total_pct}%.
                {mode === "arrear" && anyRule.reattempt_internal === "keep" && " The first attempt's internal mark is kept."}
              </p>
            )}
            <div className="att-table-wrap">
              <table className="att-table">
                <thead>
                  <tr>
                    <th>Sl.No</th>
                    <th>Student Name</th>
                    <th>Roll No</th>
                    {mode === "arrear" && <th className="center">Now</th>}
                    {split ? (
                      <>
                        <th className="center">Internal{anyRule ? ` / ${anyRule.internal_max}` : ""}</th>
                        <th className="center">End-sem{anyRule ? ` / ${anyRule.end_max}` : ""}</th>
                      </>
                    ) : (
                      <th className="center">Marks / {maxMarks}</th>
                    )}
                    <th className="center">Grade</th>
                    <th className="center">Result</th>
                    {handGrades.length > 0 && <th className="center">By hand</th>}
                  </tr>
                </thead>
                <tbody>
                  {students.map((e, idx) => {
                    const pv = preview(e.student);
                    const rule = ruleOf(e.student);
                    return (
                      <tr key={e.student} className={rowErrors[e.student] ? "cr-row-bad" : ""}>
                        <td>{idx + 1}</td>
                        <td className="att-td-name">{e.student_name}
                          {rowErrors[e.student] && <div className="cr-row-err">{rowErrors[e.student]}</div>}</td>
                        <td><span className="att-roll">{e.student_roll_no || "—"}</span></td>
                        {mode === "arrear" && <td className="center"><b>{e.grade}</b><div className="cr-muted">attempt {e.attempt}{e.exam_session ? ` · ${e.exam_session}` : ""}</div></td>}
                        {split ? (
                          rule ? (
                            <>
                              <td className="center">{numInput(e.student, "internal", rule.internal_max, `${e.student_name}: internal`)}</td>
                              <td className="center">{numInput(e.student, "end", rule.end_max, `${e.student_name}: end-semester`)}</td>
                            </>
                          ) : (
                            <td className="center" colSpan={2}>{numInput(e.student, "total", maxMarks, `${e.student_name}: marks`)}<div className="cr-muted">no regulation: total / {maxMarks}</div></td>
                          )
                        ) : (
                          <td className="center">{numInput(e.student, "total", maxMarks, `${e.student_name}: marks`)}</td>
                        )}
                        <td className="center"><b>{pv ? pv.grade : "—"}</b></td>
                        <td className="center">
                          {!pv || pv.pass == null ? (
                            <span style={{ color: "#85839A" }}>{pv?.note || "—"}</span>
                          ) : pv.pass ? (
                            <span style={{ color: "#16a34a", fontSize: 14 }}>Pass</span>
                          ) : (
                            <span style={{ color: "#dc2626", fontSize: 14 }}>{pv.note === "absent" ? "Absent" : pv.note === "not counted" ? "Not counted" : "Arrear"}</span>
                          )}
                        </td>
                        {handGrades.length > 0 && (
                          <td className="center">
                            <select className="att-input" style={{ width: 84 }} aria-label={`${e.student_name}: grade by hand`}
                              value={(rows[e.student] || blankRow).hand} disabled={!rule}
                              onChange={(ev) => setCell(e.student, "hand", ev.target.value)}>
                              <option value="">—</option>
                              {(rule?.hand_grades || []).map((g) => <option key={g} value={g}>{g}</option>)}
                            </select>
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Save bar */}
            <div className="att-save-bar">
              <button className={`att-save-btn${saving ? " loading" : ""}`}
                onClick={saveResults} disabled={saving}>
                {saving ? "Saving…" : mode === "arrear" ? "Save re-exam marks" : "Save Marks"}
              </button>
              <span style={{ fontSize: 13.5, color: "#5D5A6B" }}>Blank marks = absent. Grades are worked out on the server when you save.</span>
            </div>

            {/* Publish bar */}
            {mode === "regular" && (
              <div className="att-save-bar" style={{ marginTop: 8, borderTop: "1px solid #eee", paddingTop: 12 }}>
                <span style={{ fontSize: 14, color: "#5D5A6B" }}>
                  Once all subjects for Semester {chosenTA?.semester} are entered, publish to release results to students.
                </span>
                <button className="att-btn-outline" onClick={publishSemester} disabled={publishing}>
                  {publishing ? "Publishing…" : `Publish Semester ${chosenTA?.semester}`}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );

  if (embedded) return body;

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="att-page">{body}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
