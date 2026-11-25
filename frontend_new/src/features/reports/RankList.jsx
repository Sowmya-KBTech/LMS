// WAVE 1 - class rank list for one semester (published results).
// /rank-list : class in-charges (their class), HODs (their department), admins.
import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import { errorText, getRankList, getReportClasses, pctTone, roman } from "./reportsApi";
import "../../App.css";
import "../../styles/Reports.css";

const fmt = (n) => (n == null ? "—" : Number(n).toFixed(2).replace(/\.00$/, ""));

export default function RankList() {
  const [open, setOpen] = useState(false);
  const [classes, setClasses] = useState(null);
  const [pick, setPick] = useState("");            // "course-year"
  const [semester, setSemester] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getReportClasses()
      .then((rows) => {
        setClasses(rows);
        const first = rows.find((r) => r.semesters.length) || rows[0];
        if (first) {
          setPick(`${first.course}-${first.year}`);
          setSemester(first.semesters.length ? String(first.semesters[first.semesters.length - 1]) : "");
        }
      })
      .catch((err) => setError(errorText(err, "Couldn't load your classes.")));
  }, []);

  const current = useMemo(
    () => (classes || []).find((c) => `${c.course}-${c.year}` === pick),
    [classes, pick],
  );

  useEffect(() => {
    if (!current || !semester) { setData(null); return; }
    setLoading(true);
    setError("");
    getRankList(current.course, current.year, semester)
      .then(setData)
      .catch((err) => setError(errorText(err, "Couldn't load the rank list.")))
      .finally(() => setLoading(false));
  }, [current, semester]);

  const changeClass = (value) => {
    setPick(value);
    const c = (classes || []).find((x) => `${x.course}-${x.year}` === value);
    setSemester(c && c.semesters.length ? String(c.semesters[c.semesters.length - 1]) : "");
  };

  const firstUnranked = data ? data.rows.findIndex((r) => r.rank == null) : -1;

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="header-box">
              <h1>Rank list</h1>
              <p>
                {data ? `${data.course_name} · ${roman(data.year)} Year · Semester ${data.semester}`
                  : "Class ranks from published semester results"}
              </p>
            </div>

            <section className="kb-card no-print">
              <div className="rp-pickers">
                <label>Class
                  <select value={pick} onChange={(e) => changeClass(e.target.value)} disabled={!classes?.length}>
                    {(classes || []).map((c) => (
                      <option key={`${c.course}-${c.year}`} value={`${c.course}-${c.year}`}>
                        {c.course_name} · {roman(c.year)} Year
                      </option>
                    ))}
                  </select>
                </label>
                <label>Semester
                  <select value={semester} onChange={(e) => setSemester(e.target.value)} disabled={!current?.semesters.length}>
                    {(current?.semesters || []).map((s) => <option key={s} value={s}>Semester {s}</option>)}
                  </select>
                </label>
                <div style={{ flex: 1 }} />
                <div className="rp-actions">
                  <button type="button" className="kb-btn kb-btn--primary" onClick={() => window.print()} disabled={!data?.rows.length}>
                    Print / save as PDF
                  </button>
                </div>
              </div>
              {classes && classes.length === 0 && (
                <p className="rp-muted" style={{ marginTop: 12 }}>
                  Rank lists are for class in-charges, HODs and admins. No class is linked to you.
                </p>
              )}
              {current && current.semesters.length === 0 && (
                <p className="rp-muted" style={{ marginTop: 12 }}>No published results for this class yet.</p>
              )}
            </section>

            {error && <section className="kb-card"><p className="rp-bad">{error}</p></section>}
            {loading && <section className="kb-card"><p className="rp-muted">Loading…</p></section>}

            {data && !loading && (
              <>
                <div className="rp-stats">
                  <div className="rp-stat"><span>Appeared</span><b>{data.summary.appeared}</b></div>
                  <div className="rp-stat"><span>Cleared all subjects</span><b>{data.summary.all_clear}</b></div>
                  <div className="rp-stat"><span>Pass percentage</span><b>{fmt(data.summary.pass_percentage)}%</b></div>
                  <div className="rp-stat"><span>Class average</span><b>{fmt(data.summary.class_average)}%</b></div>
                </div>

                <section className="kb-card">
                  <h2 className="kb-at-h2">Ranks</h2>
                  <p className="rp-muted">Only students who cleared every subject are ranked. Equal percentages share a rank.</p>
                  <div style={{ overflowX: "auto" }}>
                    <table className="rp-table">
                      <thead>
                        <tr>
                          <th className="c">Rank</th><th>Roll no.</th><th>Name</th>
                          <th className="num">Total</th><th className="num">%</th><th className="c">Arrears</th>
                          <th className="no-print" />
                        </tr>
                      </thead>
                      <tbody>
                        {data.rows.length === 0 && (
                          <tr><td colSpan={7} className="rp-muted">No published results for this semester.</td></tr>
                        )}
                        {data.rows.map((r, i) => (
                          <Fragment key={r.student_id}>
                            {i === firstUnranked && (
                              <tr className="rp-sep">
                                <td colSpan={7}>Not ranked · with arrears</td>
                              </tr>
                            )}
                            <tr>
                              <td className="c">{r.rank ? <span className={`rp-rank${r.rank === 1 ? " r1" : ""}`}>{r.rank}</span> : "—"}</td>
                              <td>{r.roll_number || "—"}</td>
                              <td><b>{r.name}</b></td>
                              <td className="num">{fmt(r.total)} / {r.max}</td>
                              <td className={`num rp-${pctTone(r.percentage)}`}>{fmt(r.percentage)}</td>
                              <td className="c">{r.arrears ? <span className="rp-bad">{r.arrears}</span> : 0}</td>
                              <td className="no-print">
                                <Link to={`/progress-report/${r.student_id}`} className="kb-btn kb-btn--sm">Report</Link>
                              </td>
                            </tr>
                          </Fragment>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                {data.toppers.length > 0 && (
                  <section className="kb-card">
                    <h2 className="kb-at-h2">Subject toppers</h2>
                    <div className="rp-toppers">
                      {data.toppers.map((t) => (
                        <div className="rp-topper" key={t.subject}>
                          <h4>{t.code ? `${t.code} · ` : ""}{t.subject}</h4>
                          <ol>
                            {t.top.map((p, i) => (
                              <li key={i}>{p.name} <span className="rp-muted">({fmt(p.marks)}/{p.max})</span></li>
                            ))}
                          </ol>
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
