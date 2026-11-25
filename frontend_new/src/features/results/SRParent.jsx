// Semester results of a parent's child.
// WAVE 3 PART 1B: the same result sheet the student sees (ResultSheet).
import { useEffect, useState } from "react";
import API from "../../api";
import ResultSheet from "./ResultSheet";
import { errorText } from "./creditsUtil";
import "../../styles/Attendance.css";

export default function SRParent() {
  const [children, setChildren] = useState(null);
  const [activeChild, setActiveChild] = useState(null);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  // ---- load children (the first one is shown) ----
  useEffect(() => {
    API.get("/parent/dashboard/")
      .then((res) => {
        const list = res.data?.children || [];
        setChildren(list);
        if (list.length) setActiveChild(list[0].id);
      })
      .catch(() => setChildren([]));
  }, []);

  // ---- that child's results ----
  useEffect(() => {
    if (!activeChild) return;
    API.get(`results/credits/${activeChild}/`)
      .then((r) => { setData(r.data); setError(""); })
      .catch((err) => { setData(null); setError(errorText(err, "Couldn't load the results.")); });
  }, [activeChild]);

  return (
    <div className="att-card">
      {children && children.length > 1 && (
        <div className="pm-tabs no-print" style={{ marginBottom: 16 }}>
          {children.map((c) => (
            <div key={c.id} className={`pm-tab ${activeChild === c.id ? "active" : ""}`} onClick={() => { setData(null); setActiveChild(c.id); }}>
              {c.username}
            </div>
          ))}
        </div>
      )}
      <h2 className="att-card-title no-print">Semester Results</h2>
      {children && children.length === 0 && <div className="att-state"><p>No child is linked to your account yet.</p></div>}
      {error && <div className="att-state"><p>{error}</p></div>}
      {activeChild && !data && !error && <div className="att-state"><div className="att-spinner" /><p>Loading…</p></div>}
      {data && <ResultSheet key={activeChild} data={data} creditsLink="/parent/credits" />}
    </div>
  );
}
