import { useEffect, useState } from "react";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import API from "../../api";
import "../../App.css";

// ================= DESIGN TOKENS (match App.css) =================
const BRAND = "#4B32C3";
const INK = "#17151F";
const MUTED = "#5D5A6B";
const LINE = "#E7E7EC";
const HAIR = "#ECECF0";

const TYPE_COLOR = {
  holiday: { bg: "#fef2f2", text: "#dc2626", dot: "#dc2626", border: "#fecaca" },
  exam:    { bg: "#fff7ed", text: "#8A4B0A", dot: "#f59e0b", border: "#fed7aa" },
  event:   { bg: "#ecfdf3", text: "#15803d", dot: "#16a34a", border: "#bbf7d0" },
};

const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const DAYS = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];

// The API may return the type under `event_type` (model/payload field) OR `type`
// depending on the serializer. Read both so colours are correct either way.
const getType = (ev) => (ev.event_type || ev.type || "event");
// Normalise any date value to a YYYY-MM-DD key (handles plain dates AND ISO datetimes).
const dkey = (x) => String(x || "").slice(0, 10);

export default function Calendar() {
  const user = JSON.parse(localStorage.getItem("user") || "{}");
  const isAdmin = (user.role || "").toLowerCase() === "admin";

  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());

  const [title, setTitle] = useState("");
  const [type, setType] = useState("event");
  const [audience, setAudience] = useState("everyone");
  const [yearNum, setYearNum] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const showYear = audience === "students" || audience === "parents";

  const fetchEvents = () => {
    setLoading(true);
    API.get(`/calendar-feed/?month=${viewMonth + 1}&year=${viewYear}`)
      .then((res) => setEvents(res.data?.results || res.data || []))
      .catch((err) => console.log("calendar error:", err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchEvents();
    // eslint-disable-next-line
  }, [viewMonth, viewYear]);

  const addEvent = async () => {
    if (!title.trim() || !startDate) {
      alert("Please enter a title and start date.");
      return;
    }
    const payload = {
      title: title.trim(),
      event_type: type,
      audience: audience,
      year_number: showYear && yearNum ? parseInt(yearNum, 10) : null,
      start_date: startDate,
      end_date: endDate || null,
    };
    try {
      await API.post("/events/", payload);
      setTitle("");
      setStartDate("");
      setEndDate("");
      fetchEvents();
    } catch (err) {
      console.log("add error:", err);
      alert("Could not add the entry.");
    }
  };

  const deleteEvent = async (id) => {
    if (typeof id !== "string" || !id.startsWith("event-")) return;
    if (!window.confirm("Delete this entry?")) return;
    const realId = id.replace("event-", "");
    try {
      await API.delete(`/events/${realId}/`);
      fetchEvents();
    } catch (err) {
      console.log("delete error:", err);
    }
  };

  const inRange = (dayStr, ev) => {
    const start = dkey(ev.start_date);
    const end = dkey(ev.end_date || ev.start_date);
    return dayStr >= start && dayStr <= end;
  };

  const prevMonth = () => {
    const d = new Date(viewYear, viewMonth - 1, 1);
    setViewMonth(d.getMonth());
    setViewYear(d.getFullYear());
  };
  const nextMonth = () => {
    const d = new Date(viewYear, viewMonth + 1, 1);
    setViewMonth(d.getMonth());
    setViewYear(d.getFullYear());
  };
  const goToday = () => {
    const d = new Date();
    setViewMonth(d.getMonth()); setViewYear(d.getFullYear());
  };

  const firstDay = new Date(viewYear, viewMonth, 1).getDay();
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let n = 1; n <= daysInMonth; n++) cells.push(n);

  const pad = (x) => String(x).padStart(2, "0");
  const monthEvents = events;

  const audienceText = (a) => {
    const k = (a || "").toLowerCase();
    if (k === "everyone") return "Everyone";
    if (k === "teachers") return "Teachers";
    if (k === "students") return "Students";
    if (k === "parents") return "Parents";
    return a;
  };

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            {/* ── HEADER ── */}
            <div className="header-box">
              <h2>Academic Calendar</h2>
              <p>
                {isAdmin ? "Add holidays, exams and events. Choose who each entry is for." : "Holidays, events and exam dates"}
              </p>
            </div>

            {/* ── LEGEND ── */}
            <div style={{ display: "flex", gap: 18, flexWrap: "wrap", fontSize: 14, marginTop: -6 }}>
              <Legend color="#dc2626" label="Holiday / leave" />
              <Legend color="#f59e0b" label="Exam" />
              <Legend color="#16a34a" label="Event" />
            </div>

            <div style={{
              display: "grid",
              gridTemplateColumns: isAdmin ? "minmax(0,300px) minmax(0,1fr)" : "minmax(0,1fr) minmax(0,260px)",
              gap: 18, alignItems: "start",
            }}>

              {/* LEFT: admin form (always visible) */}
              {isAdmin && (
                <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                  <div style={cardStyle}>
                    <h3 style={h3Style}>Add entry</h3>

                    <Label>Title</Label>
                    <input style={inputStyle} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Final year farewell" />

                    <Label>Type</Label>
                    <select style={inputStyle} value={type} onChange={(e) => setType(e.target.value)}>
                      <option value="event">Event</option>
                      <option value="holiday">Holiday / leave</option>
                    </select>

                    <Label>Who is this for?</Label>
                    <select style={inputStyle} value={audience} onChange={(e) => setAudience(e.target.value)}>
                      <option value="everyone">Everyone</option>
                      <option value="teachers">Teachers</option>
                      <option value="students">Students</option>
                      <option value="parents">Parents</option>
                    </select>

                    {showYear && (
                      <>
                        <Label>Which year? (blank = all)</Label>
                        <select style={inputStyle} value={yearNum} onChange={(e) => setYearNum(e.target.value)}>
                          <option value="">All years</option>
                          <option value="1">First year</option>
                          <option value="2">Second year</option>
                          <option value="3">Third year</option>
                          <option value="4">Final year</option>
                        </select>
                      </>
                    )}

                    <Label>Start date</Label>
                    <input type="date" style={inputStyle} value={startDate} onChange={(e) => setStartDate(e.target.value)} />

                    <Label>End date (optional)</Label>
                    <input type="date" style={inputStyle} value={endDate} onChange={(e) => setEndDate(e.target.value)} />
                    <div style={{ fontSize: 13.5, color: MUTED, marginTop: 6, lineHeight: 1.5 }}>
                      Leave the end date blank for a single-day entry.
                    </div>

                    <button className="btn-primary" onClick={addEvent} style={{ width: "100%", marginTop: 16, padding: "11px 16px" }}>
                      Add &amp; notify
                    </button>
                  </div>

                  <div style={cardStyle}>
                    <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12, color: INK }}>This month's entries</div>
                    {monthEvents.length === 0 ? (
                      <div style={{ color: "#85839A", fontSize: 14.5 }}>No entries this month.</div>
                    ) : monthEvents.map((ev) => (
                      <div key={ev.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 0", borderBottom: `1px solid ${HAIR}`, fontSize: 14.5 }}>
                        <span style={{ width: 9, height: 9, borderRadius: "50%", background: (TYPE_COLOR[getType(ev)] || {}).dot, flexShrink: 0 }} />
                        <span style={{ flex: 1 }}>
                          {ev.title}
                          {ev.audience && (
                            <span style={{ fontSize: 12.5, color: "#85839A" }}>
                              {" · "}{audienceText(ev.audience)}
                            </span>
                          )}
                        </span>
                        {typeof ev.id === "string" && ev.id.startsWith("event-") && (
                          <button className="btn-delete" onClick={() => deleteEvent(ev.id)}>Delete</button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* CALENDAR */}
              <div style={cardStyle}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
                  <button onClick={prevMonth} style={navIcon} aria-label="Previous month">‹</button>
                  <h3 style={{ fontSize: 17, fontWeight: 600, margin: 0, color: INK }}>{MONTHS[viewMonth]} {viewYear}</h3>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="btn-primary" onClick={goToday} style={{ padding: "7px 16px", fontSize: 14 }}>Today</button>
                    <button onClick={nextMonth} style={navIcon} aria-label="Next month">›</button>
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 8, marginBottom: 8 }}>
                  {DAYS.map((d) => (
                    <div key={d} style={{ textAlign: "center", fontSize: 13, color: MUTED, fontWeight: 600, textTransform: "none", letterSpacing: 0 }}>{d}</div>
                  ))}
                </div>

                {loading ? (
                  <div style={{ padding: 48, textAlign: "center", color: "#85839A" }}>Loading…</div>
                ) : (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 8 }}>
                    {cells.map((n, idx) => {
                      if (n === null) return <div key={"e" + idx} />;
                      const dayStr = `${viewYear}-${pad(viewMonth + 1)}-${pad(n)}`;
                      const dayEvents = events.filter((ev) => inRange(dayStr, ev));
                      const isToday = dayStr === todayStr;
                      const isSunday = new Date(viewYear, viewMonth, n).getDay() === 0;
                      return (
                        <div key={dayStr} style={{
                          minHeight: 88,
                          border: isToday ? `1.5px solid ${BRAND}` : `1px solid ${LINE}`,
                          borderRadius: 10,
                          padding: 7,
                          background: isToday ? "#EEEAFB" : (isSunday ? "#F6F6F8" : "#fff"),
                        }}>
                          <div style={{
                            fontWeight: 600, fontSize: 14,
                            color: isToday ? BRAND : (isSunday ? "#85839A" : "#5D5A6B"),
                            display: "inline-flex", justifyContent: "center", alignItems: "center",
                            minWidth: isToday ? 22 : "auto", height: isToday ? 22 : "auto",
                            borderRadius: isToday ? "50%" : 0,
                            background: isToday ? "#DCD3FF" : "transparent",
                          }}>{n}</div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 4 }}>
                            {dayEvents.map((ev) => {
                              const c = TYPE_COLOR[getType(ev)] || TYPE_COLOR.event;
                              return (
                                <div key={ev.id} title={ev.title} style={{
                                  fontSize: 11.5, padding: "2px 6px", borderRadius: 6,
                                  background: c.bg, color: c.text, border: `1px solid ${c.border}`,
                                  fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                                }}>
                                  {ev.title}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* RIGHT: upcoming (non-admin only) */}
              {!isAdmin && (
                <div style={cardStyle}>
                  <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12, color: INK }}>Upcoming</div>
                  {events.length === 0 ? (
                    <div style={{ color: "#85839A", fontSize: 14.5 }}>Nothing scheduled.</div>
                  ) : events.slice(0, 8).map((ev) => (
                    <div key={ev.id} style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 0", borderBottom: `1px solid ${HAIR}`, fontSize: 14.5 }}>
                      <span style={{ width: 9, height: 9, borderRadius: "50%", background: (TYPE_COLOR[getType(ev)] || {}).dot, flexShrink: 0 }} />
                      <span style={{ flex: 1 }}>{ev.title}</span>
                      <span style={{ color: "#85839A", fontSize: 13, fontWeight: 500 }}>{dkey(ev.start_date).slice(8, 10)}/{dkey(ev.start_date).slice(5, 7)}</span>
                    </div>
                  ))}
                </div>
              )}

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Legend({ color, label }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 7, color: "#5D5A6B", fontWeight: 500 }}>
      <span style={{ width: 11, height: 11, borderRadius: "50%", background: color, display: "inline-block" }} />
      {label}
    </span>
  );
}

function Label({ children }) {
  return <div style={{ fontSize: 13.5, color: MUTED, marginBottom: 6, marginTop: 12, fontWeight: 500 }}>{children}</div>;
}

const cardStyle = { background: "#fff", border: `1px solid ${LINE}`, borderRadius: 14, padding: 22, boxShadow: "0 1px 3px rgba(16,24,40,0.04)" };
const h3Style = { fontSize: 17, fontWeight: 600, marginBottom: 15, color: INK };
const inputStyle = { width: "100%", border: "1px solid #E7E7EC", borderRadius: 9, padding: "10px 12px", fontSize: 15, background: "#fff", outline: "none", fontFamily: "inherit", boxSizing: "border-box", color: "#17151F" };
const navIcon = { border: "1px solid #E7E7EC", background: "#fff", borderRadius: 9, padding: "5px 15px", cursor: "pointer", fontSize: 18, fontWeight: 600, color: "#5D5A6B", lineHeight: 1 };