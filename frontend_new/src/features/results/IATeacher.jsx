import { useEffect, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../styles/Attendance.css";
import ImportExport from "../../components/ImportExport";
import { IAPaperAndMarks } from "../outcomes/CoMarks";   // CO-PO PART B

const IA_NUMBERS = [
  { num: 1, label: "IA 1" },
  { num: 2, label: "IA 2" },
  { num: 3, label: "IA 3" },
];

// FIX #14: a mark is valid when blank (not entered), or a number 0..max.
// Returns an error text, or "" when the value is fine.
const markError = (value, max) => {
  if (value === "" || value == null) return "";
  const n = Number(value);
  if (Number.isNaN(n)) return "Enter a number";
  if (n < 0) return "Cannot be negative";
  if (n > max) return `Maximum is ${max}`;
  return "";
};

export default function IATeacher({ embedded = false }) {
  const [open, setOpen] = useState(false);

  const [subjects, setSubjects]     = useState([]);
  const [selectedTA, setSelectedTA] = useState("");
  const [iaNumber, setIaNumber]     = useState(1);
  const [maxMarks, setMaxMarks]     = useState(50);

  const [students, setStudents]     = useState([]);
  const [marks, setMarks]           = useState({}); // { studentId: { value, absent } }
  const [isLocked, setIsLocked]     = useState(false);

  const [loading, setLoading]       = useState(false);
  const [saving, setSaving]         = useState(false);
  const [saved, setSaved]           = useState(false);
  const [qwise, setQwise]           = useState(false);  // CO-PO PART B: this IA has a question paper

  // ── teacher's own subjects ──
  useEffect(() => {
    API.get("/teaching-assignments/?my=true").then((res) => {
      setSubjects(res.data?.results || res.data || []);
    });
  }, []);

  // ── roster when subject changes ──
  useEffect(() => {
    if (!selectedTA) { setStudents([]); setMarks({}); return; }
    setLoading(true);
    API.get(`/enrollments/?teaching_assignment=${selectedTA}`)
      .then((res) => {
        const data = Array.isArray(res.data) ? res.data : (res.data?.results || []);
        setStudents(data);
      })
      .finally(() => setLoading(false));
  }, [selectedTA]);

  // ── existing marks + lock state when subject/IA/roster changes ──
  const loadMarks = () => {
    if (!selectedTA || students.length === 0) return;

    const init = {};
    students.forEach((e) => { init[e.student] = { value: "", absent: false }; });

    API.get(`/internal-assessments/?teaching_assignment=${selectedTA}`)
      .then((res) => {
        const slots = res.data?.results || res.data || [];
        const slot = slots.find((s) => Number(s.number) === Number(iaNumber));
        if (slot) {
          setIsLocked(!!slot.is_locked);
          setMaxMarks(slot.max_marks || 50);
          (slot.marks || []).forEach((m) => {
            init[m.student] = {
              value: m.marks_obtained ?? "",
              absent: !!m.is_absent,
            };
          });
        } else {
          setIsLocked(false);
          setMaxMarks(50);
        }
        setMarks(init);
      });
  };

  useEffect(() => {
    loadMarks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTA, iaNumber, students]);

  const setValue = (studentId, value) => {
    setMarks((prev) => ({
      ...prev,
      [studentId]: { ...prev[studentId], value },
    }));
  };

  const toggleAbsent = (studentId) => {
    setMarks((prev) => {
      const cur = prev[studentId] || { value: "", absent: false };
      const absent = !cur.absent;
      return { ...prev, [studentId]: { value: absent ? "" : cur.value, absent } };
    });
  };

  const saveMarks = async () => {
    if (!selectedTA) return alert("Please select a subject.");
    if (isLocked) return;

    // FIX #14: refuse to send anything while a mark is out of range
    const bad = students
      .map((e) => {
        const cell = marks[e.student] || {};
        const msg = cell.absent ? "" : markError(cell.value, maxMarks);
        return msg ? `${e.student_name}: ${cell.value} (${msg})` : null;
      })
      .filter(Boolean);
    if (bad.length) {
      alert(
        `Marks not saved. Marks must be between 0 and ${maxMarks}.\n\n` +
        bad.join("\n")
      );
      return;
    }

    setSaving(true);
    const records = students.map((e) => {
      const cell = marks[e.student] || {};
      return {
        student: e.student,
        is_absent: !!cell.absent,
        marks_obtained:
          cell.absent || cell.value === "" || cell.value == null
            ? null
            : Number(cell.value),
      };
    });
    try {
      await API.post("/ia-marks/save_marks/", {
        teaching_assignment: selectedTA,
        number: iaNumber,
        max_marks: maxMarks,
        records,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      const data = err.response?.data;
      const msg =
        data?.detail ||
        (Array.isArray(data) ? data.join(" ") : null) ||
        "Error saving marks. Please try again.";
      alert(msg);
    } finally {
      setSaving(false);
    }
  };

  // summary
  const entered = students.filter((e) => {
    const c = marks[e.student];
    return c && !c.absent && c.value !== "" && c.value != null;
  }).length;
  const absentCount = students.filter((e) => marks[e.student]?.absent).length;
  const avg = (() => {
    const vals = students
      .map((e) => marks[e.student])
      .filter((c) => c && !c.absent && c.value !== "" && c.value != null)
      .map((c) => (Number(c.value) / maxMarks) * 100);
    if (!vals.length) return null;
    return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1);
  })();

  const body = (
    <>
      <div className="att-header">
        <div>
          <h1 className="att-title">Internal Assessment</h1>
          <p className="att-subtitle">Enter IA marks for your subjects</p>
        </div>
      </div>

      <div className="att-card">
        <h2 className="att-card-title">Enter Marks</h2>

        {/* Filters */}
        <div className="att-filter-grid">
          <div className="att-field">
            <label className="att-label">Subject</label>
            <select
              className="att-input"
              value={selectedTA}
              onChange={(e) => setSelectedTA(e.target.value)}
            >
              <option value="">— Select Subject —</option>
              {subjects.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.subject_name} — {s.course_name} (Year {s.year_number}, Sem {s.semester})
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

        {/* CO-PO PART B: question paper (each question tagged to a CO) and marks by question */}
        {selectedTA && (
          <IAPaperAndMarks key={`${selectedTA}-${iaNumber}`} ta={selectedTA} number={iaNumber}
            onMode={setQwise} />
        )}

        {/* Import / Export (shared engine) — once a subject is chosen.
            A locked IA can still be exported, but not imported. */}
        {selectedTA && !qwise && (
          <div className="kb-io-bar">
            <ImportExport
              importer="ia_marks"
              label="marks"
              matchLabel="roll number"
              modes={["upsert"]}
              options={{ teaching_assignment: selectedTA, number: iaNumber, max_marks: maxMarks }}
              note={`Marks out of ${maxMarks} · AB = absent · blank = unchanged. The template already lists your students.`}
              canImport={!isLocked}
              onDone={loadMarks}
            />
          </div>
        )}

        {/* Lock banner */}
        {isLocked && (
          <div className="att-state" style={{ color: "#8A4B0A" }}>
            <p>This IA is locked by admin and declared to students — entry is read-only.</p>
          </div>
        )}

        {/* States / table */}
        {qwise ? null : loading ? (
          <div className="att-state"><div className="att-spinner" /><p>Loading students…</p></div>
        ) : !selectedTA ? (
          <div className="att-state"><p>Select a subject above to enter marks.</p></div>
        ) : students.length === 0 ? (
          <div className="att-state"><p>No students enrolled in this subject.</p></div>
        ) : (
          <>
            <div className="att-table-wrap">
              <table className="att-table">
                <thead>
                  <tr>
                    <th>Sl.No</th>
                    <th>Student Name</th>
                    <th>Roll No</th>
                    <th className="center">Marks / {maxMarks}</th>
                    <th className="center">Absent</th>
                  </tr>
                </thead>
                <tbody>
                  {students.map((e, idx) => {
                    const cell = marks[e.student] || { value: "", absent: false };
                    return (
                      <tr key={e.id}>
                        <td>{idx + 1}</td>
                        <td className="att-td-name">{e.student_name}</td>
                        <td><span className="att-roll">{e.student_roll_no || "—"}</span></td>
                        <td className="center">
                          {cell.absent ? (
                            <span style={{ color: "#85839A", fontWeight: 600 }}>AB</span>
                          ) : (
                            <>
                              <input
                                className="att-input"
                                type="number"
                                min={0}
                                max={maxMarks}
                                step="0.5"
                                style={{
                                  width: 80,
                                  textAlign: "center",
                                  ...(markError(cell.value, maxMarks)
                                    ? { borderColor: "#dc2626", background: "#fef2f2", color: "#b91c1c" }
                                    : {}),
                                }}
                                disabled={isLocked}
                                value={cell.value}
                                aria-invalid={!!markError(cell.value, maxMarks)}
                                onChange={(ev) => setValue(e.student, ev.target.value)}
                              />
                              {markError(cell.value, maxMarks) && (
                                <div style={{ color: "#b91c1c", fontSize: 12.5, marginTop: 4 }}>
                                  {markError(cell.value, maxMarks)}
                                </div>
                              )}
                            </>
                          )}
                        </td>
                        <td className="center">
                          <button
                            className={`att-status-btn absent${cell.absent ? " active" : ""}`}
                            disabled={isLocked}
                            onClick={() => toggleAbsent(e.student)}
                          >
                            AB
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Summary */}
            <div className="att-summary-row">
              <span className="att-chip present">{entered} Entered</span>
              <span className="att-chip duty">{avg != null ? `${avg}% Avg` : "—"}</span>
              <span className="att-chip absent">{absentCount} Absent</span>
            </div>

            {/* Save bar */}
            <div className="att-save-bar">
              <button
                className={`att-save-btn${saving ? " loading" : ""}`}
                onClick={saveMarks}
                disabled={saving || isLocked}
              >
                {saving ? "Saving…" : "Save Marks"}
              </button>
              {saved && <span className="att-saved-msg">Marks saved successfully</span>}
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