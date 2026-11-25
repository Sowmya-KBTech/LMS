import { useEffect, useState } from "react";
import API from "../../api";
import "../../styles/Attendance.css";

export default function IAParent() {
  const [children, setChildren] = useState([]);
  const [activeChild, setActiveChild] = useState(null);
  const [marks, setMarks] = useState([]);
  const [loading, setLoading] = useState(true);

  // ---- load children (same endpoint your attendance screen uses) ----
  useEffect(() => {
    API.get("/parent/dashboard/")
      .then((res) => setChildren(res.data?.children || []))
      .catch((err) => console.log("children fetch error:", err));
  }, []);

  // ---- load IA marks for selected child (or all) ----
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const q = activeChild ? `?child=${activeChild}` : "";
        const res = await API.get(`/ia-marks/${q}`);
        setMarks(res.data?.results || res.data || []);
      } catch (err) {
        console.log("ia marks error:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChild]);

  return (
    <div className="att-card">
      {/* child selector tabs */}
      <div className="pm-tabs" style={{ marginBottom: 16 }}>
        <div
          className={`pm-tab ${activeChild === null ? "active" : ""}`}
          onClick={() => setActiveChild(null)}
        >
          All Children
        </div>
        {children.map((c) => (
          <div
            key={c.id}
            className={`pm-tab ${activeChild === c.id ? "active" : ""}`}
            onClick={() => setActiveChild(c.id)}
          >
            {c.username}
          </div>
        ))}
      </div>

      <h2 className="att-card-title">Internal Assessment Marks</h2>

      {loading ? (
        <div className="att-state"><div className="att-spinner" /><p>Loading…</p></div>
      ) : marks.length === 0 ? (
        <div className="att-state"><p>No declared internal assessment marks yet.</p></div>
      ) : (
        <table className="att-table" style={{ width: "100%" }}>
          <thead>
            <tr>
              <th>Child</th>
              <th>Subject</th>
              <th>Assessment</th>
              <th style={{ textAlign: "center" }}>Marks</th>
              <th style={{ textAlign: "center" }}>Max</th>
            </tr>
          </thead>
          <tbody>
            {marks.map((m) => (
              <tr key={m.id}>
                <td>{m.student_name || "—"}</td>
                <td>{m.subject_name || m.assessment?.subject_name || "—"}</td>
                <td>IA {m.assessment_number || m.assessment?.number || ""}</td>
                <td style={{ textAlign: "center" }}>
                  {m.is_absent ? "Absent" : (m.marks_obtained ?? "—")}
                </td>
                <td style={{ textAlign: "center" }}>
                  {m.max_marks || m.assessment?.max_marks || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}