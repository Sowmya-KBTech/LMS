import { useEffect, useState } from "react";

import API from "../../api";

const STATUS = {
  draft:     { bg: "#ECECF0", fg: "#5D5A6B", bd: "#E7E7EC", label: "Draft" },
  submitted: { bg: "#fff7ed", fg: "#8A4B0A", bd: "#fed7aa", label: "Submitted" },
  approved:  { bg: "#ecfdf5", fg: "#15803d", bd: "#bbf7d0", label: "Approved" },
  rejected:  { bg: "#fef2f2", fg: "#dc2626", bd: "#fecaca", label: "Rejected" },
};

// Monday to Friday. Saturday was removed from TimetableEntry.day_of_week, so
// nothing can be stored against it any more.
//
// DAYS.length is load-bearing in three places below - the grid header, the
// break row's colSpan, and weekCapacity - so the overbooked check follows this
// array automatically. Expect it to start firing on classes that only fitted
// because of the sixth day.
const DAYS = [
  { value: 0, label: "Mon" },
  { value: 1, label: "Tue" },
  { value: 2, label: "Wed" },
  { value: 3, label: "Thu" },
  { value: 4, label: "Fri" },
];

const MAX_PER_DAY = 5;

const fmt = (t) => {
  if (!t) return "";
  const [h, m] = String(t).split(":");
  let hour = parseInt(h, 10);
  const ampm = hour >= 12 ? "PM" : "AM";
  hour = hour % 12 || 12;
  return `${hour}:${m} ${ampm}`;
};

export default function ApprovalsPanel() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState(null);         // { text, tone }

  const [review, setReview] = useState(null);
  const [slots, setSlots] = useState([]);
  const [entries, setEntries] = useState([]);
  const [options, setOptions] = useState([]);
  const [classActs, setClassActs] = useState([]);   // what this class is SUPPOSED to have
  const [busy, setBusy] = useState(false);
  const [remark, setRemark] = useState("");
  const [remarkError, setRemarkError] = useState("");

  const [rejecting, setRejecting] = useState(null);
  const [listRemark, setListRemark] = useState("");

  // MEETING POINT 5: tone "ok" = green, "bad" = red. An error stays longer
  // so the admin can read why the approval was refused.
  const showToast = (msg, tone = "ok") => {
    setToast({ text: msg, tone });
    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => setToast(null), tone === "bad" ? 6000 : 2200);
  };

  const load = async () => {
    setLoading(true);
    try {
      const r = await API.get("/timetable/approvals/");
      setRows(r.data || []);
    } catch (err) {
      console.error("Approvals load error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    API.get("/timeslots/").then((r) => setSlots(r.data || [])).catch(() => {});
  }, []);

  const openReview = async (row) => {
    const yearId = row.year ?? row.year_id;
    if (!yearId) {
      showToast("This class is missing a year id — cannot open the grid.", "bad");
      return;
    }

    setBusy(true);
    setReview(row);
    setRemark("");
    setRemarkError("");

    const q = `year=${yearId}&semester=${row.semester}`;
    try {
      const [e, o, ca] = await Promise.all([
        API.get(`/timetable/?${q}`),
        API.get(`/timetable/options/?${q}`),
        API.get(`/class-activities/?${q}`).catch(() => ({ data: [] })),
      ]);
      setEntries(e.data || []);
      setOptions(o.data || []);
      setClassActs(ca.data || []);
    } catch (err) {
      console.error("Review load error:", err);
      setEntries([]);
      setOptions([]);
      setClassActs([]);
    } finally {
      setBusy(false);
    }
  };

  const closeReview = () => {
    setReview(null);
    setEntries([]);
    setOptions([]);
    setClassActs([]);
  };

  const act = async (id, action, note) => {
    try {
      await API.post(`/timetable/approvals/${id}/action/`, {
        action,
        remark: (note || "").trim(),
      });
      showToast(
        action === "approve"
          ? "✓ Approved — published to teachers and students"
          : "✓ Rejected — sent back to the HOD"
      );
      closeReview();
      setRejecting(null);
      setListRemark("");
      load();
    } catch (err) {
      console.error(`${action} error:`, err);
      // MEETING POINT 5: show the backend's reason (clash at approval,
      // or the timetable is no longer submitted) instead of a generic line.
      const data = err?.response?.data || {};
      const n = (data.conflicts || []).length;
      showToast(
        data.detail
          ? data.detail + (n ? ` (${n} clash${n > 1 ? "es" : ""})` : "")
          : "Could not save that decision.",
        "bad"
      );
      load();   // the status may have changed meanwhile — refresh the queue
    }
  };

  const rejectFromReview = () => {
    if (!remark.trim()) {
      setRemarkError("Tell the HOD what to change — a reason is required.");
      return;
    }
    act(review.id, "reject", remark);
  };

  // ================================================================
  //  THE CHECKS
  // ================================================================
  const lookup = {};
  entries.forEach((e) => {
    lookup[`${e.day_of_week}_${e.time_slot}`] = e;
  });

  // Split the two kinds ONCE, at the top. Everything below reads from these.
  const subjectEntries = entries.filter((e) => e.kind !== "activity");
  const activityEntries = entries.filter((e) => e.kind === "activity");

  const totalNeed = options.reduce((n, o) => n + (o.weekly_hours || 0), 0);
  const totalPlaced = subjectEntries.length;

  // total teaching cells in the week — what the HOD actually has to work with
  const teachingSlots = slots.filter((s) => !s.is_break).length;
  const weekCapacity = teachingSlots * DAYS.length;
  const activityNeed = classActs.reduce((n, c) => n + (c.periods_per_week || 0), 0);
  const overbooked = totalNeed + activityNeed - weekCapacity;

  // subjects short of their weekly hours
  const shortSubjects = options
    .map((o) => {
      const done = subjectEntries.filter((e) => e.assignment === o.id).length;
      const need = o.weekly_hours || 0;
      return { name: o.subject, teacher: o.teacher_name, short: need - done, need };
    })
    .filter((s) => s.short > 0);

  // activities short of their weekly periods
  const shortActs = classActs
    .map((c) => {
      const done = activityEntries.filter((e) => e.class_activity === c.id).length;
      const need = c.periods_per_week || 0;
      return { name: c.name, short: need - done, need, done };
    })
    .filter((a) => a.short > 0);

  // teachers over the daily limit, within this timetable.
  // An unsupervised activity has teacher_name = null — it must not become a
  // phantom teacher called "null" with six periods on Monday.
  const perTeacherDay = {};
  entries.forEach((e) => {
    if (!e.teacher_name) return;
    const k = `${e.teacher_name}|${e.day_of_week}`;
    perTeacherDay[k] = (perTeacherDay[k] || 0) + 1;
  });

  const heavyDays = Object.entries(perTeacherDay)
    .filter(([, n]) => n > MAX_PER_DAY)
    .map(([k, n]) => {
      const [name, day] = k.split("|");
      return { name, day: DAYS[Number(day)]?.label || "?", count: n };
    });

  const teacherCount = new Set(
    entries.map((e) => e.teacher_name).filter(Boolean)
  ).size;

  const warnings =
    shortSubjects.length + shortActs.length + heavyDays.length + (overbooked > 0 ? 1 : 0);

  const pending = rows.filter((r) => r.status === "submitted");
  const others = rows.filter((r) => r.status !== "submitted");

  const cls = (r) => `${r.course || "—"} · Year ${r.year_number ?? "—"} · Sem ${r.semester}`;

  // ================================================================
  //  REVIEW
  // ================================================================
  if (review) {
    return (
      <div>
        {toast && <Toast text={toast.text} tone={toast.tone} />}

        <button className="tb-cancel" style={{ marginBottom: 14 }} onClick={closeReview}>
          ← Back to queue
        </button>

        <div style={{ display: "flex", gap: 12, marginBottom: 18, flexWrap: "wrap" }}>
          <Tile
            label="Subject hours"
            value={`${totalPlaced} / ${totalNeed}`}
            tone={totalNeed > 0 && totalPlaced >= totalNeed ? "ok" : "warn"}
            hint="activities not counted"
          />
          <Tile
            label="Activities"
            value={`${activityEntries.length} / ${activityNeed}`}
            tone={
              activityNeed === 0
                ? "plain"
                : activityEntries.length >= activityNeed
                ? "ok"
                : "warn"
            }
          />
          <Tile label="Clashes" value="Checked" tone="ok" hint="at save, submit and approve" />
          <Tile label="Warnings" value={String(warnings)} tone={warnings ? "warn" : "ok"} />
          <Tile label="Teachers" value={String(teacherCount)} tone="plain" />
        </div>

        {/* ---------- THE GRID — this is the review ---------- */}
        <div className="tb-card">
          <h3 className="tb-card-title">{cls(review)}</h3>
          <p className="tb-hint" style={{ marginTop: 0, marginBottom: 14 }}>
            Read-only. To change anything, reject it back to {review.submitted_by || "the HOD"}.
          </p>

          {busy ? (
            <p className="tb-state">Loading…</p>
          ) : entries.length === 0 ? (
            <p className="tb-state">This timetable has no entries.</p>
          ) : (
            <div className="tb-wrap" style={{ border: "none", boxShadow: "none", padding: 0 }}>
              <table className="tb-grid">
                <thead>
                  <tr>
                    <th className="tb-corner">Period</th>
                    {DAYS.map((d) => <th key={d.value}>{d.label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {slots.map((slot) =>
                    slot.is_break ? (
                      <tr key={slot.id} className="tb-brkrow">
                        <td className="tb-per">
                          {slot.label || "Break"}
                          <span>{fmt(slot.start_time)}–{fmt(slot.end_time)}</span>
                        </td>
                        <td colSpan={DAYS.length}>{slot.label || "Break"}</td>
                      </tr>
                    ) : (
                      <tr key={slot.id}>
                        <td className="tb-per">
                          P{slot.period_no}
                          <span>{fmt(slot.start_time)}–{fmt(slot.end_time)}</span>
                        </td>
                        {DAYS.map((d) => {
                          const e = lookup[`${d.value}_${slot.id}`];
                          const isAct = e?.kind === "activity";

                          // An activity carries its own colour. A lecture is blue.
                          // Rendering them identically hides the thing the admin
                          // is being asked to check.
                          const style = isAct && e.activity_colour
                            ? {
                                cursor: "default",
                                background: `${e.activity_colour}22`,
                                borderColor: e.activity_colour,
                                color: e.activity_colour,
                              }
                            : { cursor: "default" };

                          let cellCls = "tb-cell";
                          if (e) cellCls += isAct ? " tb-cell-act" : " tb-cell-has";

                          return (
                            <td key={d.value}>
                              <div className={cellCls} style={style}>
                                {e ? (
                                  <>
                                    <strong>{e.subject}</strong>
                                    <small>
                                      {isAct
                                        ? (e.teacher_name || "activity")
                                        : (e.room_name || e.teacher_name)}
                                    </small>
                                  </>
                                ) : (
                                  <span className="tb-free">—</span>
                                )}
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ---------- CHECKS — a line each, detail only when wrong ---------- */}
        {!busy && entries.length > 0 && (
          <div className="tb-card">
            <h3 className="tb-card-title">Checks</h3>

            {/* The week is a fixed number of cells. If the subjects alone claim
                all of them, no activity can ever be placed — and the HOD cannot
                fix that from the timetable screen. Say so, don't make the admin
                work it out from the grid. */}
            {overbooked > 0 && (
              <Check>
                <strong>The week is overbooked.</strong> {totalNeed} subject hours
                {activityNeed > 0 && ` + ${activityNeed} activity periods`} = {totalNeed + activityNeed},
                but the week only has {weekCapacity} cells. {overbooked} period
                {overbooked === 1 ? "" : "s"} cannot fit anywhere.
                <div style={{ fontSize: 14, color: "#5D5A6B", marginTop: 4 }}>
                  Reduce the weekly hours in Faculty Allocation — a 1-credit subject
                  does not need 4 periods a week.
                </div>
              </Check>
            )}

            {shortSubjects.length === 0 ? (
              <Check ok>All {options.length} subjects have their full weekly hours.</Check>
            ) : (
              <Check>
                {shortSubjects.length === 1
                  ? "1 subject is short of hours:"
                  : `${shortSubjects.length} subjects are short of hours:`}
                <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
                  {shortSubjects.map((s) => (
                    <li key={s.name} style={{ fontSize: 14.5, marginBottom: 2 }}>
                      <strong>{s.name}</strong> ({s.teacher}) — {s.short} of {s.need} missing
                    </li>
                  ))}
                </ul>
              </Check>
            )}

            {/* This is the check the admin was doing by eye when they wrote
                "there is no library period or the playing period". */}
            {classActs.length === 0 ? (
              <Check ok>This class has no activities configured.</Check>
            ) : shortActs.length === 0 ? (
              <Check ok>
                All {classActs.length} activities are on the grid
                ({classActs.map((c) => c.name).join(", ")}).
              </Check>
            ) : (
              <Check>
                {shortActs.length === 1
                  ? "1 activity is missing periods:"
                  : `${shortActs.length} activities are missing periods:`}
                <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
                  {shortActs.map((a) => (
                    <li key={a.name} style={{ fontSize: 14.5, marginBottom: 2 }}>
                      <strong>{a.name}</strong> — {a.done} of {a.need} placed
                    </li>
                  ))}
                </ul>
              </Check>
            )}

            {heavyDays.length === 0 ? (
              <Check ok>No teacher exceeds {MAX_PER_DAY} periods in a day.</Check>
            ) : (
              <Check>
                Heavy days:
                <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>
                  {heavyDays.map((o) => (
                    <li key={`${o.name}${o.day}`} style={{ fontSize: 14.5, marginBottom: 2 }}>
                      <strong>{o.name}</strong> has {o.count} periods on {o.day}
                    </li>
                  ))}
                </ul>
              </Check>
            )}

            <Check ok>
              Teacher, room and class clashes were blocked at save and submit. They are
              checked once more when you approve — if another class has taken a slot
              since, the approval is refused and the reason is shown.
            </Check>
          </div>
        )}

        {/* ---------- DECISION — only a SUBMITTED timetable can be decided on ---------- */}
        {review.status === "submitted" ? (
        <div className="tb-card">
          <h3 className="tb-card-title">Decision</h3>
          <p className="tb-hint" style={{ marginTop: 0, marginBottom: 12 }}>
            Rejecting releases every slot this timetable is holding, so other departments
            can use them straight away.
          </p>

          <textarea
            value={remark}
            onChange={(e) => { setRemark(e.target.value); setRemarkError(""); }}
            placeholder="Reason — the HOD will see this. Required when rejecting."
            style={{
              width: "100%", minHeight: 78, padding: "10px 12px", fontSize: 15,
              fontFamily: "inherit",
              border: `1px solid ${remarkError ? "#dc2626" : "#E7E7EC"}`,
              borderRadius: 10, resize: "vertical", color: "#17151F", background: "#fbfcfe",
            }}
          />
          {remarkError && <div className="tb-error">{remarkError}</div>}

          <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
            <button className="tb-del" onClick={rejectFromReview}>
              Reject and return to HOD
            </button>
            <button
              className="tb-btn"
              style={{ background: "#15803d" }}
              onClick={() => act(review.id, "approve", remark)}
            >
              Approve and publish
            </button>
          </div>
        </div>
        ) : (
          <div className="tb-card">
            <h3 className="tb-card-title">Decision</h3>
            <p className="tb-hint" style={{ margin: 0 }}>
              This timetable is <Badge status={review.status} /> — only a submitted
              timetable can be approved or rejected.
            </p>
          </div>
        )}
      </div>
    );
  }

  // ================================================================
  //  QUEUE
  // ================================================================
  return (
    <div>
      {toast && <Toast text={toast.text} tone={toast.tone} />}

      <div className="tb-card">
        <h3 className="tb-card-title">Pending approval ({pending.length})</h3>
        <p className="tb-hint" style={{ marginTop: 0, marginBottom: 16 }}>
          Clashes were already blocked when the HOD built this. You're checking the plan.
        </p>

        {loading ? (
          <p className="tb-state">Loading…</p>
        ) : pending.length === 0 ? (
          <p className="tb-state">No timetables waiting for approval.</p>
        ) : (
          <table className="tb-list">
            <thead>
              <tr>
                <th>Class</th>
                <th>Submitted by</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((r) => (
                <tr key={r.id}>
                  <td><strong>{cls(r)}</strong></td>
                  <td>{r.submitted_by || "—"}</td>
                  <td className="tb-right">
                    {rejecting === r.id ? (
                      <div className="tb-edit-cell">
                        <input
                          value={listRemark}
                          placeholder="Reason for the HOD"
                          onChange={(e) => setListRemark(e.target.value)}
                          style={{ minWidth: 180 }}
                        />
                        <button
                          className="tb-btn tb-btn-sm"
                          onClick={() => {
                            if (!listRemark.trim()) return;
                            act(r.id, "reject", listRemark);
                          }}
                        >
                          Confirm
                        </button>
                        <button
                          className="tb-cancel"
                          onClick={() => { setRejecting(null); setListRemark(""); }}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="tb-actions">
                        <button className="tb-edit" onClick={() => openReview(r)}>
                          Review
                        </button>
                        <button
                          className="tb-btn tb-btn-sm"
                          style={{ background: "#15803d" }}
                          onClick={() => act(r.id, "approve")}
                        >
                          Approve
                        </button>
                        <button
                          className="tb-del"
                          onClick={() => { setRejecting(r.id); setListRemark(""); }}
                        >
                          Reject
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {!loading && others.length > 0 && (
        <div className="tb-card">
          <h3 className="tb-card-title">All timetables</h3>
          <table className="tb-list">
            <thead>
              <tr>
                <th>Class</th>
                <th>Status</th>
                <th>Note</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {others.map((r) => (
                <tr key={r.id}>
                  <td><strong>{cls(r)}</strong></td>
                  <td><Badge status={r.status} /></td>
                  <td style={{ color: r.status === "rejected" ? "#dc2626" : "#5D5A6B", fontSize: 14 }}>
                    {r.status === "rejected" ? (r.remark || "Rejected") : ""}
                  </td>
                  <td className="tb-right">
                    <button className="tb-cancel" onClick={() => openReview(r)}>
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ---------- small pieces ----------

function Check({ ok, children }) {
  return (
    <div
      style={{
        display: "flex", gap: 10, alignItems: "flex-start",
        padding: "10px 0", borderBottom: "1px solid #eef1f6",
        fontSize: 15, color: "#17151F",
      }}
    >
      <span
        style={{
          flex: "none", width: 18, height: 18, borderRadius: "50%",
          background: ok ? "#ecfdf5" : "#fff7ed",
          color: ok ? "#15803d" : "#8A4B0A",
          fontSize: 12, fontWeight: 700,
          display: "flex", alignItems: "center", justifyContent: "center",
          marginTop: 2,
        }}
      >
        {ok ? "✓" : "!"}
      </span>
      <div>{children}</div>
    </div>
  );
}

function Badge({ status }) {
  const s = STATUS[status] || STATUS.draft;
  return (
    <span
      style={{
        display: "inline-block", fontSize: 13, fontWeight: 700,
        color: s.fg, background: s.bg, border: `1px solid ${s.bd}`,
        borderRadius: 999, padding: "3px 12px", whiteSpace: "nowrap",
      }}
    >
      {s.label}
    </span>
  );
}

// MEETING POINT 5: red for errors, green for success
function Toast({ text, tone }) {
  return (
    <div
      role="status"
      style={{
        position: "fixed", top: 24, left: "50%", transform: "translateX(-50%)",
        zIndex: 1000, background: tone === "bad" ? "#dc2626" : "#15803d",
        color: "#fff", fontSize: 15,
        fontWeight: 600, padding: "11px 22px", borderRadius: 12,
        maxWidth: "90vw",
        boxShadow: "0 8px 24px rgba(0,0,0,.22)",
      }}
    >
      {text}
    </div>
  );
}

function Tile({ label, value, tone, hint }) {
  const colours = { ok: "#15803d", warn: "#8A4B0A", bad: "#dc2626", plain: "#17151F" };
  return (
    <div
      style={{
        flex: 1, minWidth: 140, background: "#fff", border: "1px solid #E7E7EC",
        borderRadius: 14, padding: "14px 16px",
      }}
    >
      <div style={{ fontSize: 13, color: "#5D5A6B" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 800, color: colours[tone] || "#17151F", marginTop: 3 }}>
        {value}
      </div>
      {hint && <div style={{ fontSize: 12, color: "#85839A", marginTop: 2 }}>{hint}</div>}
    </div>
  );
}