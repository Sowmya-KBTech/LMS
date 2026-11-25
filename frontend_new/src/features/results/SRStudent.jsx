// Semester results for the signed-in student.
// WAVE 3 PART 1B: under the student's regulation - internal / end-sem / total,
// grade points, SGPA with its working, and arrear attempts (ResultSheet).
import { useEffect, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import ResultSheet from "./ResultSheet";
import { errorText } from "./creditsUtil";
import "../../styles/Attendance.css";

export default function SRStudent({ embedded = false }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    API.get("results/credits/me/")
      .then((r) => setData(r.data))
      .catch((err) => setError(errorText(err, "Couldn't load your results.")));
  }, []);

  const body = (
    <>
      <div className="att-header no-print">
        <div>
          <h1 className="att-title">Semester Result</h1>
          <p className="att-subtitle">Your results under your regulation, semester by semester</p>
        </div>
      </div>
      {error && <div className="att-card"><div className="att-state"><p>{error}</p></div></div>}
      {!data && !error && <div className="att-card"><div className="att-state"><div className="att-spinner" /><p>Loading results…</p></div></div>}
      {data && <ResultSheet data={data} creditsLink="/my-credits" />}
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
