// ============================================================
// ElectiveEnroll — the STUDENT's electives page (meeting point 9, Step 3)
// ============================================================
// What the student sees depends on the college setting:
//   * "Students choose"  -> each elective group ("pick 1 of these") with
//                           seats left and the last date; Choose / Remove
//   * "HOD allocates"    -> read-only: the electives the HOD gave them
//
// All rules (own class, pick limit, seats, last date, setting) are checked
// by the server - this page only shows what the server allows.
//   GET  /electives/my/          groups, options, seats, my choices
//   POST /electives/my/choose/   { option }
//   POST /electives/my/drop/     { option }
//
// Electives the HOD has not put in any group yet still appear under
// "Other electives" (old /my-electives/ list), so nothing disappears.
// ============================================================

import { useEffect, useState } from "react";

import API from "../../api";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import "../../App.css";
import { MyCourseRegistration } from "../electives/CourseRegistration";   // CBCS PART A

const fmtDate = (iso) =>
  iso
    ? new Date(iso).toLocaleString("en-IN", {
        day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit",
      })
    : "";

const errText = (err, fallback) => err?.response?.data?.detail || fallback;

export default function ElectiveEnroll() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);       // { students_choose, groups: [...] }
  const [others, setOthers] = useState([]);     // electives not in any group (old list)
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);       // option id / TA id being saved
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [reg, setReg] = useState(null);         // CBCS PART A: course registration, when a window covers the student

  const showToast = (msg) => {
    setToast(msg);
    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => setToast(""), 2500);
  };

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [mine, old, cr] = await Promise.all([
        API.get("/electives/my/"),
        API.get("/my-electives/").catch(() => ({ data: [] })),
        API.get("/course-registration/me/").catch(() => ({ data: { window: null } })),
      ]);
      setReg(cr.data.window ? cr.data : null);
      setData(mine.data);
      // electives already shown in a group are not repeated below
      const grouped = new Set(
        (mine.data.groups || []).flatMap((g) => g.options.map((o) => o.teaching_assignment))
      );
      setOthers((old.data || []).filter((e) => !grouped.has(e.teaching_assignment)));
    } catch (err) {
      console.error("Load electives error:", err);
      setError(errText(err, "Could not load electives. Please try again."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  // ---------- grouped electives ----------
  const choose = async (option) => {
    setError("");
    setBusy(option.id);
    try {
      await API.post("/electives/my/choose/", { option: option.id });
      showToast(`You chose ${option.subject}`);
      await load();
    } catch (err) {
      setError(errText(err, "Could not save your choice."));
    } finally {
      setBusy(null);
    }
  };

  const drop = async (option) => {
    if (!window.confirm(`Remove ${option.subject}?`)) return;
    setError("");
    setBusy(option.id);
    try {
      await API.post("/electives/my/drop/", { option: option.id });
      showToast(`Removed ${option.subject}`);
      await load();
    } catch (err) {
      setError(errText(err, "Could not remove it."));
    } finally {
      setBusy(null);
    }
  };

  // ---------- electives not in any group (old behaviour) ----------
  const toggleOther = async (e) => {
    setError("");
    setBusy(`ta-${e.teaching_assignment}`);
    try {
      await API.request({
        url: "/elective-enroll/",
        method: e.enrolled ? "delete" : "post",
        data: { teaching_assignment: e.teaching_assignment },
      });
      showToast(e.enrolled ? `Removed ${e.subject}` : `Enrolled in ${e.subject}`);
      await load();
    } catch (err) {
      setError(errText(err, "Could not save that choice."));
    } finally {
      setBusy(null);
    }
  };

  const studentsChoose = data?.students_choose;
  const groups = data?.groups || [];
  const nothing = !loading && groups.length === 0 && others.length === 0;

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />

      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">
          <div className="content">
            {toast && <div className="el-toast" role="status">{toast}</div>}

            {/* CBCS PART A: inside a registration window the student registers here instead */}
            {reg && (
              <>
                <div className="header-box">
                  <h2>Course registration · Semester {reg.window.semester}</h2>
                  <p>{[reg.student.course_name, reg.student.name, reg.student.roll_number].filter(Boolean).join(" · ")}</p>
                </div>
                <MyCourseRegistration key={reg.window.id} data={reg} onChange={setReg} />
              </>
            )}

            {!reg && <>
            {/* ================= HEADER ================= */}
            <div className="header-box">
              <h2>{studentsChoose === false ? "My Electives" : "Choose Your Electives"}</h2>
              <p>
                {studentsChoose === false
                  ? "Your HOD allocates electives in this college. The electives given to you are shown below."
                  : "Pick your electives before the last date. Seats are limited — first come, first served."}
              </p>
            </div>

            {error && <div className="tb-error">{error}</div>}

            {loading && <div className="card"><p className="el-muted">Loading…</p></div>}

            {nothing && (
              <div className="card">
                <p className="el-muted">No electives are offered for your class this semester.</p>
              </div>
            )}

            {/* ================= GROUPS ================= */}
            {!loading && groups.map((g) => {
              const chosen = g.options.filter((o) => o.chosen);
              const done = chosen.length >= g.picks;
              return (
                <div className="card el-group" key={g.id}>
                  <div className="el-group-head">
                    <div>
                      <h3>{g.name}</h3>
                      <span className="el-muted">
                        {studentsChoose
                          ? `Choose ${g.picks} · ${chosen.length} of ${g.picks} chosen`
                          : chosen.length
                          ? "Allocated by your HOD"
                          : "Not allocated yet — your HOD will assign it"}
                      </span>
                    </div>
                    {studentsChoose && (
                      <span className={`el-window el-window--${g.window}`}>
                        {g.window === "not_open" && `Opens ${fmtDate(g.opens_at)}`}
                        {g.window === "open" && (g.closes_at ? `Last date ${fmtDate(g.closes_at)}` : "Open")}
                        {g.window === "closed" && "Closed — ask your HOD to change"}
                      </span>
                    )}
                  </div>

                  <ul className="el-options">
                    {g.options
                      .filter((o) => studentsChoose || o.chosen)
                      .map((o) => {
                        const seatsLeft = o.seat_limit == null ? null : Math.max(o.seat_limit - o.seats_taken, 0);
                        return (
                          <li key={o.id} className={o.chosen ? "is-chosen" : ""}>
                            <div className="el-option-info">
                              <b>{o.subject}</b>
                              <span className="el-muted">
                                {[o.code, o.teacher_name, `${o.credits ?? 0} credits`].filter(Boolean).join(" · ")}
                              </span>
                            </div>

                            {studentsChoose && (
                              <span className={`el-seats${o.is_full && !o.chosen ? " is-full" : ""}`}>
                                {seatsLeft == null
                                  ? "Open seats"
                                  : o.is_full
                                  ? "Full"
                                  : `${seatsLeft} seat${seatsLeft === 1 ? "" : "s"} left`}
                              </span>
                            )}

                            {o.chosen ? (
                              g.can_choose ? (
                                <button className="btn-delete" disabled={busy === o.id} onClick={() => drop(o)}>
                                  {busy === o.id ? "Saving…" : "Chosen ✓ — Remove"}
                                </button>
                              ) : (
                                <span className="el-chosen">✓ Your elective</span>
                              )
                            ) : (
                              g.can_choose && (
                                <button
                                  className="btn-primary"
                                  disabled={busy === o.id || o.is_full || (done && g.picks > 1)}
                                  onClick={() => choose(o)}
                                  title={done && g.picks === 1 ? "Choosing this replaces your current choice" : undefined}
                                >
                                  {busy === o.id
                                    ? "Saving…"
                                    : o.is_full
                                    ? "Full"
                                    : done && g.picks === 1
                                    ? "Switch to this"
                                    : "Choose"}
                                </button>
                              )
                            )}
                          </li>
                        );
                      })}
                  </ul>
                </div>
              );
            })}

            {/* ================= ELECTIVES NOT IN A GROUP ================= */}
            {!loading && others.length > 0 && (
              <div className="card el-group">
                <div className="el-group-head">
                  <div>
                    <h3>{groups.length ? "Other electives" : "Electives"}</h3>
                    <span className="el-muted">
                      {studentsChoose ? "Choose the ones you want." : "Allocated by your HOD."}
                    </span>
                  </div>
                </div>
                <ul className="el-options">
                  {others
                    .filter((e) => studentsChoose || e.enrolled)
                    .map((e) => (
                      <li key={e.teaching_assignment} className={e.enrolled ? "is-chosen" : ""}>
                        <div className="el-option-info">
                          <b>{e.subject}</b>
                          <span className="el-muted">
                            {[e.code, e.teacher_name, `${e.credits ?? 0} credits`].filter(Boolean).join(" · ")}
                          </span>
                        </div>
                        {studentsChoose ? (
                          <button
                            className={e.enrolled ? "btn-delete" : "btn-primary"}
                            disabled={busy === `ta-${e.teaching_assignment}`}
                            onClick={() => toggleOther(e)}
                          >
                            {busy === `ta-${e.teaching_assignment}`
                              ? "Saving…"
                              : e.enrolled
                              ? "Chosen ✓ — Remove"
                              : "Choose"}
                          </button>
                        ) : (
                          <span className="el-chosen">✓ Your elective</span>
                        )}
                      </li>
                    ))}
                </ul>
              </div>
            )}
            </>}
          </div>
        </div>
      </div>
    </div>
  );
}