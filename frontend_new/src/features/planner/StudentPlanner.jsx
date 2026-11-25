// WAVE 1 - student planner: classes, deadlines, exams and events in one place.
//   /planner          a student
//   /parent/planner   a parent (child picker when they have more than one)
// Two views: Week (a list per day) and Month (a calendar grid).
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import API from "../../api";
import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import "../../App.css";
import "../../styles/Reports.css";
import "../../styles/Planner.css";

const DAY = 86400000;
const iso = (d) => {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return z.toISOString().slice(0, 10);
};
const parse = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const mondayOf = (d) => { const x = new Date(d); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; };
const fmtDay = (s) => parse(s).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
const monthName = (d) => d.toLocaleDateString("en-GB", { month: "long", year: "numeric" });

const TYPE = {
  assignment: { label: "Assignment", tone: "blue" },
  quiz: { label: "Quiz", tone: "violet" },
  exam: { label: "Exam", tone: "red" },
  live: { label: "Live class", tone: "green" },
  event: { label: "Event", tone: "amber" },
};
const STATUS = {
  submitted: { text: "Submitted", tone: "ok" },
  attempted: { text: "Attempted", tone: "ok" },
  pending: { text: "To do", tone: "warn" },
  overdue: { text: "Overdue", tone: "bad" },
};

function itemLink(it, forParent) {
  if (forParent) return null;
  if (it.type === "assignment" || it.type === "quiz") return "/student/courses";
  if (it.type === "exam") return "/results";
  if (it.type === "event") return "/calendar";
  return null;
}

function Item({ it, forParent }) {
  const t = TYPE[it.type] || { label: it.type, tone: "gray" };
  const st = STATUS[it.status];
  const to = itemLink(it, forParent);
  const body = (
    <>
      <span className={`pl-tag ${t.tone}`}>{it.type === "event" ? it.status : t.label}</span>
      <span className="pl-item-main">
        <b>{it.title}</b>
        <small>
          {it.subject && it.type !== "exam" ? `${it.subject} · ` : ""}
          {it.type === "exam" ? it.status : it.time ? (it.type === "live" ? `at ${it.time}` : `due ${it.time}`) : ""}
        </small>
      </span>
      {st && <span className={`kb-pill ${st.tone}`}>{st.text}</span>}
    </>
  );
  if (it.type === "live" && it.link && !forParent) {
    return <a className="pl-item" href={it.link} target="_blank" rel="noreferrer">{body}</a>;
  }
  return to ? <Link className="pl-item" to={to}>{body}</Link> : <div className="pl-item">{body}</div>;
}

function DayCard({ day, today, forParent }) {
  const empty = !day.classes.length && !day.items.length;
  return (
    <section className={`pl-day${day.date === today ? " is-today" : ""}`}>
      <header>
        <b>{day.weekday}</b>
        <span>{fmtDay(day.date)}{day.date === today ? " · Today" : ""}</span>
        {day.holiday && <span className="kb-pill">{day.holiday}</span>}
        {day.on_leave && <span className="kb-pill warn">On leave</span>}
      </header>
      {day.classes.length > 0 && (
        <ol className="pl-classes">
          {day.classes.map((c) => (
            <li key={c.period}>
              <span className="pl-time">{c.start}–{c.end}</span>
              <span className="pl-item-main">
                <b>{c.subject}</b>
                <small>{[c.code, c.teacher, c.room].filter(Boolean).join(" · ")}</small>
              </span>
            </li>
          ))}
        </ol>
      )}
      {day.items.map((it, i) => <Item key={`${it.type}-${it.id}-${i}`} it={it} forParent={forParent} />)}
      {empty && <p className="pl-none">{day.holiday || (["Saturday", "Sunday"].includes(day.weekday) ? "Weekend" : "Nothing planned")}</p>}
    </section>
  );
}

function MonthGrid({ data, month, today, onPick }) {
  const byDate = useMemo(() => Object.fromEntries(data.days.map((d) => [d.date, d])), [data]);
  return (
    <div className="pl-month">
      {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((w) => <div key={w} className="pl-mhead">{w}</div>)}
      {data.days.map((d) => {
        const day = byDate[d.date];
        const out = parse(d.date).getMonth() !== month;
        const dots = day.items.slice(0, 4);
        return (
          <button type="button" key={d.date} onClick={() => onPick(d.date)}
            className={`pl-mcell${out ? " out" : ""}${d.date === today ? " is-today" : ""}${day.holiday || day.on_leave ? " off" : ""}`}>
            <span className="pl-mnum">{parse(d.date).getDate()}</span>
            {day.classes.length > 0 && <span className="pl-mclasses">{day.classes.length} class{day.classes.length > 1 ? "es" : ""}</span>}
            {day.holiday && <span className="pl-mclasses">{day.holiday}</span>}
            {day.on_leave && <span className="pl-mclasses">On leave</span>}
            <span className="pl-mdots">
              {dots.map((it, i) => <i key={i} className={TYPE[it.type]?.tone || "gray"} title={it.title} />)}
              {day.items.length > 4 && <em>+{day.items.length - 4}</em>}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function Planner({ childId, forParent }) {
  const [view, setView] = useState("week");
  const [anchor, setAnchor] = useState(() => new Date());
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const range = useMemo(() => {
    if (view === "week") return { start: mondayOf(anchor), days: 7 };
    const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    return { start: mondayOf(first), days: 42 };
  }, [view, anchor]);

  useEffect(() => {
    setError("");
    const params = { start: iso(range.start), days: range.days };
    if (childId) params.child = childId;
    API.get("planner/", { params })
      .then((r) => setData(r.data))
      .catch((err) => setError(err?.response?.data?.detail || "Couldn't load the planner."));
  }, [range, childId]);

  const move = (dir) => {
    const x = new Date(anchor);
    if (view === "week") x.setTime(x.getTime() + dir * 7 * DAY);
    else x.setMonth(x.getMonth() + dir, 1);
    setAnchor(x);
  };

  const title = view === "week"
    ? `${fmtDay(iso(range.start))} – ${fmtDay(iso(new Date(range.start.getTime() + 6 * DAY)))}`
    : monthName(anchor);

  return (
    <>
      <div className="pl-bar">
        <div className="pl-seg" role="tablist">
          {["week", "month"].map((v) => (
            <button key={v} type="button" role="tab" aria-selected={view === v}
              className={view === v ? "on" : ""} onClick={() => setView(v)}>
              {v === "week" ? "Week" : "Month"}
            </button>
          ))}
        </div>
        <div className="pl-nav">
          <button type="button" className="kb-btn kb-btn--sm" onClick={() => move(-1)} aria-label="Previous">‹</button>
          <b>{title}</b>
          <button type="button" className="kb-btn kb-btn--sm" onClick={() => move(1)} aria-label="Next">›</button>
          <button type="button" className="kb-btn kb-btn--sm" onClick={() => setAnchor(new Date())}>Today</button>
        </div>
      </div>

      {error && <section className="kb-card"><p className="rp-bad">{error}</p></section>}

      {data && (
        <div className="pl-stats">
          <div><span>Classes</span><b>{data.summary.classes}</b></div>
          <div><span>To do</span><b>{data.summary.due}</b></div>
          <div className={data.summary.overdue ? "bad" : ""}><span>Overdue</span><b>{data.summary.overdue}</b></div>
          <div><span>Exams</span><b>{data.summary.exams}</b></div>
        </div>
      )}

      {data && view === "week" && (
        <div className="pl-week">
          {data.days.map((d) => <DayCard key={d.date} day={d} today={data.today} forParent={forParent} />)}
        </div>
      )}

      {data && view === "month" && (
        <MonthGrid data={data} month={anchor.getMonth()} today={data.today}
          onPick={(d) => { setAnchor(parse(d)); setView("week"); }} />
      )}

      <p className="pl-legend">
        {Object.entries(TYPE).map(([k, t]) => <span key={k}><i className={t.tone} />{t.label}</span>)}
      </p>
    </>
  );
}

function Shell({ title, subtitle, children }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="header-box"><h1>{title}</h1><p>{subtitle}</p></div>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

/** /planner */
export default function StudentPlanner() {
  return (
    <Shell title="My planner" subtitle="Your classes, deadlines, exams and college events, day by day.">
      <Planner />
    </Shell>
  );
}

/** /parent/planner */
export function ParentPlanner() {
  const [kids, setKids] = useState(null);
  const [child, setChild] = useState(null);
  useEffect(() => {
    API.get("/parent/dashboard/")
      .then((res) => {
        const list = res.data?.children || [];
        setKids(list);
        if (list.length) setChild(list[0].id);
      })
      .catch(() => setKids([]));
  }, []);
  return (
    <Shell title="Planner" subtitle="Your child's classes, deadlines, exams and college events.">
      {kids && kids.length > 1 && (
        <div className="rp-kids">
          {kids.map((k) => (
            <button key={k.id} type="button" onClick={() => setChild(k.id)}
              className={`kb-btn kb-btn--sm${child === k.id ? " kb-btn--primary" : ""}`}>{k.username}</button>
          ))}
        </div>
      )}
      {kids && kids.length === 0 && <section className="kb-card"><p className="rp-muted">No child is linked to your account yet.</p></section>}
      {child && <Planner childId={child} forParent />}
    </Shell>
  );
}
