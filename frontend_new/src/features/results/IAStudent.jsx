import { useEffect, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../styles/Attendance.css";

const IA_NUMBERS = [1, 2, 3];

export default function IAStudent({ embedded = false }) {
  const [open, setOpen]       = useState(false);
  const [marks, setMarks]     = useState([]);
  const [loading, setLoading] = useState(true);

  // ── own IA marks (backend returns only locked/declared slots) ──
  useEffect(() => {
    API.get("/ia-marks/")
      .then((res) => setMarks(res.data?.results || res.data || []))
      .finally(() => setLoading(false));
  }, []);

  // ── group flat marks list by subject ──
  const bySubject = {};
  marks.forEach((m) => {
    const key = m.subject_name || "—";
    if (!bySubject[key]) {
      bySubject[key] = { subject: key, slots: {} };
    }
    bySubject[key].slots[m.ia_number] = m;
  });
  const rows = Object.values(bySubject);

  const cellContent = (slot) => {
    if (!slot) return <span style={{ color: "#85839A" }}>—</span>;
    if (slot.is_absent) return <span style={{ color: "#dc2626" }}>AB</span>;
    return (
      <span>
        <b>{slot.marks_obtained}</b>
        <span style={{ color: "#85839A", fontSize: 13 }}>/{slot.max_marks}</span>
      </span>
    );
  };

  const avgFor = (slots) => {
    const vals = Object.values(slots)
      .filter((s) => !s.is_absent && s.marks_obtained != null)
      .map((s) => (Number(s.marks_obtained) / Number(s.max_marks)) * 100);
    if (!vals.length) return null;
    return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(0);
  };

  // ── inner content (shared by embedded + standalone) ──
  const body = (
    <>
      <div className="att-header">
        <div>
          <h1 className="att-title">Internal Assessment</h1>
          <p className="att-subtitle">Your IA marks across subjects</p>
        </div>
      </div>

      <div className="att-card">
        <h2 className="att-card-title">My Marks</h2>

        {loading ? (
          <div className="att-state"><div className="att-spinner" /><p>Loading marks…</p></div>
        ) : rows.length === 0 ? (
          <div className="att-state">
            <p>No IA marks have been declared yet. They'll appear here once your teacher's entry is reviewed and locked.</p>
          </div>
        ) : (
          <div className="att-table-wrap">
            <table className="att-table">
              <thead>
                <tr>
                  <th>Subject</th>
                  {IA_NUMBERS.map((n) => (
                    <th key={n} className="center">IA {n}</th>
                  ))}
                  <th className="center">Average</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, idx) => {
                  const avg = avgFor(r.slots);
                  return (
                    <tr key={idx}>
                      <td className="att-td-name">{r.subject}</td>
                      {IA_NUMBERS.map((n) => (
                        <td key={n} className="center">{cellContent(r.slots[n])}</td>
                      ))}
                      <td className="center">
                        {avg != null
                          ? <span className="att-chip present">{avg}%</span>
                          : <span style={{ color: "#85839A" }}>—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
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