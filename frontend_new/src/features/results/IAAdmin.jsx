import { useEffect, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../styles/Attendance.css";

const IA_NUMBERS = [
  { num: 1, label: "IA 1" },
  { num: 2, label: "IA 2" },
  { num: 3, label: "IA 3" },
];

export default function IAAdmin({ embedded = false }) {
  const [open, setOpen] = useState(false);

  const [subjects, setSubjects]   = useState([]);   // all teaching assignments
  const [selectedCourse, setSelectedCourse] = useState("");
  const [selectedYear, setSelectedYear]     = useState("");
  const [selectedTA, setSelectedTA] = useState("");
  const [iaNumber, setIaNumber]     = useState(1);

  const [slot, setSlot]         = useState(null);   // IA slot for selected subject+number
  const [students, setStudents] = useState([]);     // enrolled roster
  const [loading, setLoading]   = useState(false);
  const [working, setWorking]   = useState(false);  // lock/unlock in progress

  // ── all teaching assignments (admin sees every subject) ──
  useEffect(() => {
    API.get("/teaching-assignments/").then((res) => {
      setSubjects(res.data?.results || res.data || []);
    });
  }, []);

  // ── derived filter lists ──
  // unique courses
  const courses = [...new Set(subjects.map((s) => s.course_name))].sort();

  // years within the chosen course
  const years = selectedCourse
    ? [...new Set(
        subjects
          .filter((s) => s.course_name === selectedCourse)
          .map((s) => s.year_number)
      )].sort((a, b) => a - b)
    : [];

  // subjects narrowed by course + year
  const filteredSubjects = subjects.filter((s) =>
    (!selectedCourse || s.course_name === selectedCourse) &&
    (!selectedYear || String(s.year_number) === String(selectedYear))
  );

  // ── load the IA slot (+ its marks) and the roster ──
  const loadSlot = () => {
    if (!selectedTA) { setSlot(null); setStudents([]); return; }
    setLoading(true);

    Promise.all([
      API.get(`/internal-assessments/?teaching_assignment=${selectedTA}`),
      API.get(`/enrollments/?teaching_assignment=${selectedTA}`),
    ])
      .then(([iaRes, enrRes]) => {
        const slots = iaRes.data?.results || iaRes.data || [];
        const found = slots.find((s) => Number(s.number) === Number(iaNumber)) || null;
        setSlot(found);

        const roster = Array.isArray(enrRes.data)
          ? enrRes.data
          : (enrRes.data?.results || []);
        setStudents(roster);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadSlot();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTA, iaNumber]);

  // studentId -> mark row (from the slot's nested marks)
  const markFor = (studentId) => {
    if (!slot || !slot.marks) return null;
    return slot.marks.find((m) => Number(m.student) === Number(studentId)) || null;
  };

  const toggleLock = async () => {
    if (!slot) return;
    setWorking(true);
    const url = slot.is_locked
      ? `/internal-assessments/${slot.id}/unlock/`
      : `/internal-assessments/${slot.id}/lock/`;
    try {
      await API.post(url);
      loadSlot();
    } catch (err) {
      alert(err.response?.data?.detail || "Action failed. Please try again.");
    } finally {
      setWorking(false);
    }
  };

  const enteredCount = slot && slot.marks
    ? slot.marks.filter((m) => m.is_absent || m.marks_obtained != null).length
    : 0;

  const body = (
    <>
      <div className="att-header">
        <div>
          <h1 className="att-title">Internal Assessment — Review</h1>
          <p className="att-subtitle">Review teacher marks and lock to declare</p>
        </div>
      </div>

      <div className="att-card">
        <h2 className="att-card-title">Review &amp; Declare</h2>

        {/* Cascading filters: Course → Year → Subject */}
        <div className="att-filter-grid">
          {/* Course */}
          <div className="att-field">
            <label className="att-label">Course</label>
            <select
              className="att-input"
              value={selectedCourse}
              onChange={(e) => {
                setSelectedCourse(e.target.value);
                setSelectedYear("");
                setSelectedTA("");
              }}
            >
              <option value="">— All Courses —</option>
              {courses.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          {/* Year */}
          <div className="att-field">
            <label className="att-label">Year</label>
            <select
              className="att-input"
              value={selectedYear}
              onChange={(e) => {
                setSelectedYear(e.target.value);
                setSelectedTA("");
              }}
              disabled={!selectedCourse}
            >
              <option value="">— All Years —</option>
              {years.map((y) => (
                <option key={y} value={y}>Year {y}</option>
              ))}
            </select>
          </div>

          {/* Subject (narrowed) */}
          <div className="att-field">
            <label className="att-label">Subject</label>
            <select
              className="att-input"
              value={selectedTA}
              onChange={(e) => setSelectedTA(e.target.value)}
            >
              <option value="">— Select Subject —</option>
              {filteredSubjects.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.subject_name} (Sem {s.semester})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* IA selector */}
        <div className="att-tabs" style={{ marginTop: 4 }}>
          {IA_NUMBERS.map((ia) => (
            <button
              key={ia.num}
              className={`att-tab${iaNumber === ia.num ? " active" : ""}`}
              onClick={() => setIaNumber(ia.num)}
            >
              {ia.label}
            </button>
          ))}
        </div>

        {/* States / table */}
        {loading ? (
          <div className="att-state"><div className="att-spinner" /><p>Loading…</p></div>
        ) : !selectedTA ? (
          <div className="att-state"><p>Select a subject to review IA marks.</p></div>
        ) : !slot ? (
          <div className="att-state">
            <p>The teacher hasn't started this IA yet — no marks to review.</p>
          </div>
        ) : (
          <>
            {/* Status + lock control */}
            <div className="att-summary-row" style={{ alignItems: "center" }}>
              <span className={`att-chip ${slot.is_locked ? "present" : "duty"}`}>
                {slot.is_locked ? "Declared (locked)" : "Draft — not declared"}
              </span>
              <span className="att-chip">{enteredCount} / {students.length} entered</span>
              <span className="att-chip">Max {slot.max_marks}</span>

              <button
                className="att-save-btn"
                style={{ marginLeft: "auto" }}
                onClick={toggleLock}
                disabled={working}
              >
                {working
                  ? "Working…"
                  : slot.is_locked
                  ? "Unlock"
                  : "Lock & Declare"}
              </button>
            </div>

            <div className="att-table-wrap">
              <table className="att-table">
                <thead>
                  <tr>
                    <th>Sl.No</th>
                    <th>Student Name</th>
                    <th>Roll No</th>
                    <th className="center">Marks / {slot.max_marks}</th>
                    <th className="center">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((e, idx) => {
                    const m = markFor(e.student);
                    return (
                      <tr key={e.id}>
                        <td>{idx + 1}</td>
                        <td className="att-td-name">{e.student_name}</td>
                        <td><span className="att-roll">{e.student_roll_no || "—"}</span></td>
                        <td className="center">
                          {!m ? (
                            <span style={{ color: "#85839A" }}>—</span>
                          ) : m.is_absent ? (
                            <span style={{ color: "#dc2626", fontWeight: 600 }}>AB</span>
                          ) : (
                            <b>{m.marks_obtained}</b>
                          )}
                        </td>
                        <td className="center">
                          {!m || (m.marks_obtained == null && !m.is_absent) ? (
                            <span style={{ color: "#85839A", fontSize: 14 }}>Pending</span>
                          ) : m.is_absent ? (
                            <span style={{ color: "#dc2626", fontSize: 14 }}>Absent</span>
                          ) : (
                            <span style={{ color: "#16a34a", fontSize: 14 }}>Entered</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
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
            <div className="att-page">
              {body}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}