import { useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import PeriodsPanel from "./PeriodsPanel";
import GridPanel from "./GridPanel";
import ApprovalsPanel from "./ApprovalsPanel";

import "../../App.css";
import "../../styles/TimetableBuilder.css";

export default function TimetableBuilder() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("periods"); // periods is step 1

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />

      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">
          <div className="tb">
            <header className="tb-head">
              <h1>Timetable Setup</h1>
              <p>Set the daily periods first, then build each class's grid. HODs build their own department's timetables; you review and approve them here.</p>
            </header>

            <div className="tb-tabs">
              <button
                className={tab === "periods" ? "active" : ""}
                onClick={() => setTab("periods")}
              >
                1 · Periods
              </button>
              <button
                className={tab === "grid" ? "active" : ""}
                onClick={() => setTab("grid")}
              >
                2 · Timetable Builder
              </button>
              <button
                className={tab === "approvals" ? "active" : ""}
                onClick={() => setTab("approvals")}
              >
                3 · Approvals
              </button>
            </div>

            {tab === "periods" && <PeriodsPanel />}
            {tab === "grid" && <GridPanel goToPeriods={() => setTab("periods")} />}
            {tab === "approvals" && <ApprovalsPanel />}
          </div>
        </div>
      </div>
    </div>
  );
}