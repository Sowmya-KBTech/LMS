import { useEffect, useState } from "react";

import API from "../../api";

// Panel rendered INSIDE TimetableBuilder (which provides Navbar/Sidebar/layout).
export default function HolidaysPanel() {
  // ---- semester ----
  const [sem, setSem] = useState({ name: "", start_date: "", end_date: "" });
  const [semMsg, setSemMsg] = useState("");
  const [semSaving, setSemSaving] = useState(false);

  // ---- holidays ----
  const [holidays, setHolidays] = useState([]);
  const [hol, setHol] = useState({ date: "", name: "" });
  const [holError, setHolError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const s = await API.get("/semester/");
      const active = (s.data || [])[0];
      if (active) {
        setSem({
          name: active.name || "",
          start_date: active.start_date || "",
          end_date: active.end_date || "",
        });
      }
    } catch (err) {
      console.error("Load semester error:", err);
    }
    try {
      const h = await API.get("/holidays/");
      setHolidays(h.data || []);
    } catch (err) {
      console.error("Load holidays error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const saveSemester = async () => {
    setSemMsg("");
    if (!sem.name || !sem.start_date || !sem.end_date) {
      setSemMsg("Please fill the name, start date and end date.");
      return;
    }
    setSemSaving(true);
    try {
      await API.post("/semester/", sem);
      alert("Semester saved");
    } catch (err) {
      const data = err?.response?.data;
      // surface whatever the backend actually returned
      let msg = "Could not save the semester.";
      if (data) {
        if (typeof data === "string") msg = data;
        else if (data.detail) msg = data.detail;
        else if (data.start_date) msg = "Start date: " + data.start_date[0];
        else if (data.end_date) msg = "End date: " + data.end_date[0];
        else if (data.name) msg = "Name: " + data.name[0];
        else msg = JSON.stringify(data);
      }
      setSemMsg(msg);
    } finally {
      setSemSaving(false);
    }
  };

  const addHoliday = async () => {
    setHolError("");
    if (!hol.date || !hol.name) {
      setHolError("Please pick a date and enter a name.");
      return;
    }
    try {
      await API.post("/holidays/", hol);
      setHol({ date: "", name: "" });
      load();
      alert("Holiday added");
    } catch (err) {
      const data = err?.response?.data;
      setHolError(
        data?.date?.[0] ||
          data?.detail ||
          "Could not add. A holiday on that date may already exist."
      );
    }
  };

  const removeHoliday = async (id) => {
    try {
      await API.delete(`/holidays/${id}/`);
      setHolidays((list) => list.filter((h) => h.id !== id));
      alert("Holiday deleted");
    } catch (err) {
      console.error("Delete holiday error:", err);
    }
  };

  return (
    <div>
      {/* SEMESTER */}
      <div className="tb-card">
        <h3 className="tb-card-title">Semester</h3>

        <div className="tb-form">
          <label className="tb-field">
            <span>Name</span>
            <input
              value={sem.name}
              placeholder="e.g. Even Semester 2026"
              onChange={(e) => setSem({ ...sem, name: e.target.value })}
              style={{ minWidth: "220px" }}
            />
          </label>

          <label className="tb-field">
            <span>Start date</span>
            <input
              type="date"
              value={sem.start_date}
              onChange={(e) => setSem({ ...sem, start_date: e.target.value })}
            />
          </label>

          <label className="tb-field">
            <span>End date</span>
            <input
              type="date"
              value={sem.end_date}
              onChange={(e) => setSem({ ...sem, end_date: e.target.value })}
            />
          </label>

          <button className="tb-btn" onClick={saveSemester} disabled={semSaving}>
            {semSaving ? "Saving…" : "Save"}
          </button>
        </div>

        {semMsg && <div className="tb-error">{semMsg}</div>}
        <p className="tb-hint">The date-based timetable view runs between these dates.</p>
      </div>

      {/* HOLIDAYS */}
      <div className="tb-card">
        <h3 className="tb-card-title">Holidays &amp; Special Days</h3>

        <div className="tb-form">
          <label className="tb-field">
            <span>Date</span>
            <input
              type="date"
              value={hol.date}
              onChange={(e) => setHol({ ...hol, date: e.target.value })}
            />
          </label>

          <label className="tb-field">
            <span>Name</span>
            <input
              value={hol.name}
              placeholder="e.g. Sports Day"
              onChange={(e) => setHol({ ...hol, name: e.target.value })}
              style={{ minWidth: "220px" }}
            />
          </label>

          <button className="tb-btn" onClick={addHoliday}>Add Holiday</button>
        </div>

        {holError && <div className="tb-error">{holError}</div>}

        {loading ? (
          <p className="tb-state">Loading…</p>
        ) : holidays.length === 0 ? (
          <p className="tb-state">No holidays added yet.</p>
        ) : (
          <table className="tb-list" style={{ marginTop: "10px" }}>
            <thead>
              <tr><th>Date</th><th>Name</th><th></th></tr>
            </thead>
            <tbody>
              {holidays.map((h) => (
                <tr key={h.id}>
                  <td><strong>{h.date}</strong></td>
                  <td>{h.name}</td>
                  <td className="tb-right">
                    <button className="tb-del" onClick={() => removeHoliday(h.id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}