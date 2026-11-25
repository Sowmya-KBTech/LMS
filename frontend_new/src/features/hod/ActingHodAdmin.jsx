// #50 ACTING HOD - admin dashboard (main admin only), shown on Admin > Departments.
// Design v2: summary tiles, decisions, department cards, filterable history,
// one "Assign acting HOD" pop-up. Same APIs and rules as before.
// Every status comes from the server (college date Asia/Kolkata; only APPROVED
// rows can be "active") - this file never works out a status itself.
// A 403 from users/acting-hod/ (not the main admin) hides the whole card.
import { useEffect, useMemo, useState } from "react";
import API from "../../api";

const VIOLET = "#4B32C3";

const TONE = {
  amber:  { bg: "#fffbeb", fg: "#92400e", bd: "#fde68a" },
  green:  { bg: "#ecfdf3", fg: "#15803d", bd: "#bbf7d0" },
  violet: { bg: "#efeafe", fg: VIOLET,    bd: "#d9d0fb" },
  red:    { bg: "#fef2f2", fg: "#b91c1c", bd: "#fecaca" },
  grey:   { bg: "#f3f4f6", fg: "#4b5563", bd: "#e5e7eb" },
};

// server status -> [label, tone]
const STATUS = {
  pending:     ["Pending approval", "amber"],
  active:      ["Active", "green"],
  upcoming:    ["Upcoming", "violet"],
  rejected:    ["Rejected", "red"],
  ended_early: ["Ended early", "grey"],
  finished:    ["Finished", "grey"],
  cancelled:   ["Cancelled", "grey"],
  expired:     ["Expired", "grey"],
};

// department card state -> [label, tone, sort rank]
const DEPT_STATE = {
  pending:  ["Pending", "amber", 0],
  acting:   ["Acting", "green", 1],
  upcoming: ["Upcoming", "violet", 2],
  nohod:    ["No HOD set", "grey", 3],
  normal:   ["Normal", "grey", 4],
};

const FILTERS = [
  ["all", "All", () => true],
  ["active", "Active", (s) => s === "active"],
  ["upcoming", "Upcoming", (s) => s === "upcoming"],
  ["pending", "Pending", (s) => s === "pending"],
  ["ended", "Ended", (s) => s === "ended_early" || s === "finished"],
  ["rejected", "Rejected", (s) => s === "rejected"],
  ["closed", "Cancelled / expired", (s) => s === "cancelled" || s === "expired"],
];

const PAGE = 10;
const EMPTY_FORM = { department: "", teacher: "", start_date: "", end_date: "", reason: "" };

const fmtD = (iso) => {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}-${m}-${y}`;
};
const fmtShort = (iso) => (iso ? fmtD(iso).slice(0, 5) : "—");
const fmtDT = (iso) => {
  if (!iso) return "—";
  return new Date(iso)
    .toLocaleString("en-IN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
    .replace(/\//g, "-");
};
const addDays = (iso, n) => {
  if (!iso) return "";
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  const p = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};
const errText = (err) => err?.response?.data?.detail || "Something went wrong. Please try again.";
const initials = (name) => (name || "?").replace(/[^A-Za-z]/g, "").slice(0, 2).toUpperCase();

const S = {
  muted: { fontSize: 13, color: "#6b7280" },
  section: { fontSize: 15, fontWeight: 600, margin: "22px 0 10px", color: "#1f1530" },
  smallBtn: { padding: "4px 12px", fontSize: 13, borderRadius: 6 },
  label: { display: "flex", flexDirection: "column", fontSize: 13, gap: 4, color: "#374151" },
};

function Chip({ tone, children }) {
  const t = TONE[tone] || TONE.grey;
  return (
    <span style={{
      background: t.bg, color: t.fg, border: `1px solid ${t.bd}`, padding: "2px 10px",
      borderRadius: 999, fontSize: 13, fontWeight: 600, whiteSpace: "nowrap",
    }}>{children}</span>
  );
}

const statusChip = (s) => {
  const [label, tone] = STATUS[s] || [s, "grey"];
  return <Chip tone={tone}>{label}</Chip>;
};

export default function ActingHodAdmin() {
  const [allowed, setAllowed] = useState(null);   // null = loading, false = hide
  const [data, setData] = useState({ today: "", departments: [], assignments: [] });
  const [msg, setMsg] = useState(null);           // { ok, text }
  const [busy, setBusy] = useState(false);

  // pop-up: assign / extend / end / approve / reject
  const [dialog, setDialog] = useState(null);     // { kind, a? }
  const [form, setForm] = useState(EMPTY_FORM);
  const [teachers, setTeachers] = useState([]);
  const [dlgEnd, setDlgEnd] = useState("");
  const [dlgReason, setDlgReason] = useState("");
  const [dlgErr, setDlgErr] = useState("");

  // history
  const [openLog, setOpenLog] = useState(null);
  const [search, setSearch] = useState("");
  const [deptFilter, setDeptFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [shown, setShown] = useState(PAGE);

  const load = async () => {
    try {
      const res = await API.get("users/acting-hod/");
      setData(res.data);
      setAllowed(true);
    } catch (err) {
      if (err?.response?.status === 403) {
        setAllowed(false);
      } else {
        setAllowed(true);
        setMsg({ ok: false, text: "Could not load Acting HOD assignments." });
      }
    }
  };

  useEffect(() => {
    load();
  }, []);

  const deptName = (id) => data.departments.find((d) => d.id === id)?.name || "—";
  const regularHod = (id) => data.departments.find((d) => d.id === id)?.hod_name || "—";

  // ---------- counts (from the server's statuses) ----------
  const counts = useMemo(() => {
    const c = { pending: 0, active: 0, upcoming: 0 };
    data.assignments.forEach((a) => { if (c[a.status] !== undefined) c[a.status] += 1; });
    return c;
  }, [data]);

  const pending = useMemo(
    () => data.assignments.filter((a) => a.status === "pending")
      .sort((x, y) => x.start_date.localeCompare(y.start_date)),
    [data],
  );

  // ---------- one card per department, attention first ----------
  const deptCards = useMemo(() => data.departments.map((d) => {
    const mine = data.assignments.filter((a) => a.department.id === d.id);
    const pend = mine.find((a) => a.status === "pending");
    const active = mine.find((a) => a.status === "active");
    const next = mine.filter((a) => a.status === "upcoming")
      .sort((x, y) => x.start_date.localeCompare(y.start_date))[0];
    const state = pend ? "pending" : active ? "acting" : next ? "upcoming" : !d.hod ? "nohod" : "normal";
    return { d, pend, active, next, state };
  }).sort((x, y) =>
    DEPT_STATE[x.state][2] - DEPT_STATE[y.state][2] || x.d.name.localeCompare(y.d.name)), [data]);

  // ---------- history: search + department + status work together ----------
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const test = (FILTERS.find((f) => f[0] === statusFilter) || FILTERS[0])[2];
    return data.assignments.filter((a) => {
      if (deptFilter && String(a.department.id) !== String(deptFilter)) return false;
      if (!test(a.status)) return false;
      if (!q) return true;
      return [a.teacher.username, a.reason, a.nominated_by, a.department.name, a.reject_reason, a.end_reason]
        .some((v) => (v || "").toLowerCase().includes(q));
    });
  }, [data, search, deptFilter, statusFilter]);

  const resetPaging = () => { setShown(PAGE); setOpenLog(null); };

  // ---------- pop-up ----------
  const openDialog = (kind, a = null) => {
    setDialog({ kind, a });
    setDlgEnd(""); setDlgReason(""); setDlgErr("");
    if (kind === "assign") { setForm(EMPTY_FORM); setTeachers([]); }
  };

  const pickDepartment = async (deptId) => {
    setForm((f) => ({ ...f, department: deptId, teacher: "" }));
    setTeachers([]);
    if (!deptId) return;
    try {
      const res = await API.get(`users/acting-hod/candidates/?department=${deptId}`);
      setTeachers(res.data.teachers || []);
    } catch (err) {
      setDlgErr(errText(err));
    }
  };

  const submitDialog = async () => {
    const { kind, a } = dialog;
    setDlgErr("");
    if (kind === "assign") {
      if (!form.department || !form.teacher || !form.start_date || !form.end_date) {
        setDlgErr("Fill in the department, teacher and both dates."); return;
      }
      if (form.reason.trim().length < 10) {
        setDlgErr("Please give a reason (at least 10 characters)."); return;
      }
    }
    if (kind === "extend" && !dlgEnd) { setDlgErr("Pick the new end date."); return; }
    if (["extend", "end", "reject"].includes(kind) && dlgReason.trim().length < 10) {
      setDlgErr("Please give a reason (at least 10 characters)."); return;
    }
    setBusy(true);
    try {
      if (kind === "assign") {
        const res = await API.post("users/acting-hod/", form);
        const r = res.data;
        setMsg({ ok: true, text: `✓ ${r.teacher.username} is Acting HOD of ${r.department.name} from ${fmtD(r.start_date)} to ${fmtD(r.end_date)}.` });
      } else if (kind === "extend") {
        await API.post(`users/acting-hod/${a.id}/extend/`, { end_date: dlgEnd, reason: dlgReason });
        setMsg({ ok: true, text: `✓ ${a.teacher.username}'s Acting HOD period now ends on ${fmtD(dlgEnd)}.` });
      } else if (kind === "end") {
        await API.post(`users/acting-hod/${a.id}/end/`, { reason: dlgReason });
        setMsg({ ok: true, text: a.status === "upcoming"
          ? `✓ The assignment for ${a.teacher.username} was cancelled.`
          : `✓ ${a.teacher.username}'s Acting HOD powers have ended.` });
      } else if (kind === "approve") {
        const res = await API.post(`users/acting-hod/${a.id}/approve/`);
        setMsg({ ok: true, text: `✓ Approved. ${a.teacher.username} is Acting HOD of ${a.department.name} until ${fmtD(a.end_date)}`
          + (res.data.status === "active" ? " (from now)." : ` (from ${fmtD(a.start_date)}).`) });
      } else if (kind === "reject") {
        await API.post(`users/acting-hod/${a.id}/reject/`, { reason: dlgReason });
        setMsg({ ok: true, text: `✓ Nomination rejected. ${a.nominated_by || "The HOD"} was told the reason.` });
      }
      setDialog(null);
      load();
    } catch (err) {
      setDlgErr(errText(err));
    } finally {
      setBusy(false);
    }
  };

  if (!allowed) return null;

  const tomorrow = addDays(data.today, 1);
  const startsWhen = (a) =>
    a.start_date <= data.today ? "starts today" : a.start_date === tomorrow ? "starts tomorrow" : `starts ${fmtD(a.start_date)}`;

  const tile = (label, value, warn) => (
    <div style={{
      background: warn ? TONE.amber.bg : "#f7f5fc", border: `1px solid ${warn ? TONE.amber.bd : "#ece8f6"}`,
      borderRadius: 12, padding: "12px 16px",
    }}>
      <div style={{ fontSize: 13, color: warn ? TONE.amber.fg : "#6b7280" }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color: warn ? TONE.amber.fg : "#1f1530" }}>{value}</div>
    </div>
  );

  const dlgTitle = {
    assign: "Assign acting HOD", extend: "Extend Acting HOD", approve: "Approve nomination",
    reject: "Reject nomination", end: dialog?.a?.status === "upcoming" ? "Cancel assignment" : "End Acting HOD early",
  };
  const dlgButton = {
    assign: "Assign", extend: "Extend", approve: "Approve", reject: "Reject",
    end: dialog?.a?.status === "upcoming" ? "Cancel assignment" : "End now",
  };

  return (
    <div className="card">
      {/* ---------- heading ---------- */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h3 style={{ margin: 0 }}>Acting HOD</h3>
          <p style={{ ...S.muted, fontSize: 14, margin: "4px 0 0" }}>
            Who holds HOD powers, and what needs your decision. The regular HOD in the table above does not change.
          </p>
        </div>
        <button className="btn-primary" style={{ padding: "8px 18px", borderRadius: 8, flex: "none" }}
                onClick={() => openDialog("assign")}>
          + Assign acting HOD
        </button>
      </div>

      {msg && (
        <p style={{ marginTop: 12, fontSize: 14, fontWeight: 600, color: msg.ok ? "#15803d" : "#b91c1c" }}>{msg.text}</p>
      )}

      {/* ---------- summary tiles ---------- */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12, marginTop: 16 }}>
        {tile("Waiting for you", counts.pending, counts.pending > 0)}
        {tile("Acting now", counts.active)}
        {tile("Upcoming", counts.upcoming)}
        {tile("Departments", data.departments.length)}
      </div>

      {/* ---------- needs your decision ---------- */}
      <div style={S.section}>Needs your decision</div>
      {pending.length === 0 ? (
        <p style={{ ...S.muted, fontSize: 14, margin: 0 }}>Nothing is waiting for you.</p>
      ) : pending.map((a) => (
        <div key={a.id} style={{
          display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", background: "#fff",
          border: "1px solid #ece8f6", borderLeft: "4px solid #f59e0b", borderRadius: 12,
          padding: "12px 16px", marginBottom: 10,
        }}>
          <div style={{
            width: 40, height: 40, borderRadius: "50%", background: TONE.violet.bg, color: VIOLET,
            display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 14, flex: "none",
          }}>{initials(a.teacher.username)}</div>
          <div style={{ flex: "1 1 260px", minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 15 }}>
              {a.teacher.username} <span style={{ marginLeft: 6 }}><Chip tone="violet">{a.department.name}</Chip></span>
            </div>
            <div style={{ fontSize: 14, color: "#4b5563", marginTop: 3 }}>
              {fmtD(a.start_date)} → {fmtD(a.end_date)} · nominated by {a.nominated_by || "—"} · <b>{startsWhen(a)}</b>
            </div>
            <div style={{ ...S.muted, marginTop: 2 }}>{a.reason}</div>
          </div>
          <div style={{ display: "flex", gap: 8, flex: "none" }}>
            <button className="btn-delete" onClick={() => openDialog("reject", a)}>Reject</button>
            <button className="btn-primary" style={{ padding: "6px 16px", borderRadius: 6 }}
                    onClick={() => openDialog("approve", a)}>Approve</button>
          </div>
        </div>
      ))}

      {/* ---------- departments ---------- */}
      <div style={{ ...S.section, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <span>Departments</span>
        <span style={{ display: "flex", gap: 6, flexWrap: "wrap", fontWeight: 400 }}>
          {Object.values(DEPT_STATE).map(([label, tone]) => <Chip key={label} tone={tone}>{label}</Chip>)}
        </span>
      </div>
      {data.departments.length === 0 ? (
        <p style={{ ...S.muted, fontSize: 14 }}>No departments yet.</p>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 12 }}>
          {deptCards.map(({ d, pend, active, next, state }) => {
            const [label, tone] = DEPT_STATE[state];
            return (
              <div key={d.id} style={{ background: "#fff", border: "1px solid #ece8f6", borderRadius: 12, padding: "12px 14px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
                  <div style={{ fontWeight: 600, fontSize: 15 }}>{d.name}</div>
                  <Chip tone={tone}>{label}</Chip>
                </div>
                <div style={{ ...S.muted, marginTop: 6 }}>HOD {d.hod_name || "—"}</div>

                {active && (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ fontSize: 14 }}><b>{active.teacher.username}</b> acting until {fmtShort(active.end_date)}</div>
                    <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                      <button className="btn-edit" style={S.smallBtn} onClick={() => openDialog("extend", active)}>Extend</button>
                      <button className="btn-delete" style={S.smallBtn} onClick={() => openDialog("end", active)}>End early</button>
                    </div>
                  </div>
                )}
                {next && (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ fontSize: 14 }}><b>{next.teacher.username}</b> from {fmtShort(next.start_date)} to {fmtShort(next.end_date)}</div>
                    <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                      <button className="btn-edit" style={S.smallBtn} onClick={() => openDialog("extend", next)}>Extend</button>
                      <button className="btn-delete" style={S.smallBtn} onClick={() => openDialog("end", next)}>Cancel</button>
                    </div>
                  </div>
                )}
                {pend && (
                  <div style={{ fontSize: 14, color: TONE.amber.fg, marginTop: 8 }}>
                    {pend.teacher.username} · {fmtShort(pend.start_date)} → {fmtShort(pend.end_date)} · waiting for you
                  </div>
                )}
                {!active && !next && !pend && (
                  <div style={{ ...S.muted, fontSize: 14, marginTop: 8 }}>
                    {d.hod ? "No acting HOD" : "Use “Assign acting HOD” above if needed"}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ---------- history ---------- */}
      <div style={S.section}>History</div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
        <input type="text" placeholder="Search teacher, department or reason" value={search}
               onChange={(e) => { setSearch(e.target.value); resetPaging(); }}
               style={{ flex: "1 1 240px", minWidth: 0 }} />
        <select value={deptFilter} onChange={(e) => { setDeptFilter(e.target.value); resetPaging(); }} style={{ minWidth: 190 }}>
          <option value="">All departments</option>
          {data.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        {FILTERS.map(([key, label]) => {
          const on = statusFilter === key;
          return (
            <button key={key} onClick={() => { setStatusFilter(key); resetPaging(); }}
                    style={{
                      padding: "4px 12px", borderRadius: 999, fontSize: 13, fontWeight: 600, cursor: "pointer",
                      background: on ? VIOLET : "#fff", color: on ? "#fff" : "#4b5563",
                      border: `1px solid ${on ? VIOLET : "#e5e7eb"}`,
                    }}>
              {label}
            </button>
          );
        })}
      </div>

      <div style={{ border: "1px solid #ece8f6", borderRadius: 12, overflow: "hidden" }}>
        {filtered.length === 0 && (
          <div style={{ padding: "14px 16px", ...S.muted, fontSize: 14 }}>No assignments match these filters.</div>
        )}
        {filtered.slice(0, shown).map((a, i) => {
          const open = openLog === a.id;
          const last = i === Math.min(shown, filtered.length) - 1;
          return (
            <div key={a.id} style={{ borderBottom: last && !open ? "none" : "1px solid #f0edf8" }}>
              <button onClick={() => setOpenLog(open ? null : a.id)}
                      style={{
                        width: "100%", display: "flex", alignItems: "center", gap: 10, padding: "10px 16px",
                        background: "#fff", border: "none", cursor: "pointer", textAlign: "left", fontSize: 14,
                      }}>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <b>{a.teacher.username}</b> · {a.department.name} · {fmtD(a.start_date)}
                  {a.end_date !== a.start_date ? ` → ${fmtD(a.end_date)}` : ""}
                  {a.nominated_by && <span style={{ color: "#6b7280" }}> · nominated by {a.nominated_by}</span>}
                </span>
                {statusChip(a.status)}
                <span aria-hidden="true" style={{ color: "#9ca3af", width: 14 }}>{open ? "▲" : "▼"}</span>
              </button>
              {open && (
                <div style={{ background: "#faf9ff", padding: "8px 16px 12px 30px", fontSize: 13.5, color: "#374151" }}>
                  <div style={{ ...S.muted, marginBottom: 4 }}>Regular HOD: {regularHod(a.department.id)} · Department: {deptName(a.department.id)}</div>
                  {a.log.map((l, j) => (
                    <div key={j} style={{ padding: "3px 0" }}>
                      <b>{fmtDT(l.done_at)}</b> · {l.action_label}
                      {l.action === "extended" && ` (${fmtD(l.old_end_date)} → ${fmtD(l.new_end_date)})`}
                      {" "}· by {l.done_by || "—"} · “{l.reason}”
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {filtered.length > shown && (
        <div style={{ textAlign: "center", marginTop: 10 }}>
          <button className="btn-edit" onClick={() => setShown(shown + PAGE)}>
            Show more ({filtered.length - shown} more)
          </button>
        </div>
      )}

      {/* ---------- pop-up ---------- */}
      {dialog && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(43,26,63,0.45)", display: "flex",
          alignItems: "center", justifyContent: "center", zIndex: 1000, padding: 16,
        }}>
          <div style={{ background: "#fff", borderRadius: 14, padding: 22, width: "100%", maxWidth: 480 }}>
            <h3 style={{ marginTop: 0 }}>{dlgTitle[dialog.kind]}</h3>

            {dialog.kind === "assign" ? (
              <>
                <p style={{ ...S.muted, marginTop: -6 }}>For an emergency, a vacant HOD post, or to replace a rejected nomination.</p>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                  <label style={S.label}>Department
                    <select value={form.department} onChange={(e) => pickDepartment(e.target.value)}>
                      <option value="">— Pick —</option>
                      {data.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </select>
                  </label>
                  <label style={S.label}>Acting HOD
                    <select value={form.teacher} disabled={!form.department}
                            onChange={(e) => setForm({ ...form, teacher: e.target.value })}>
                      <option value="">{form.department ? "— Pick a teacher —" : "Pick a department first"}</option>
                      {teachers.map((t) => <option key={t.id} value={t.id}>{t.username}</option>)}
                    </select>
                  </label>
                  <label style={S.label}>From
                    <input type="date" value={form.start_date} min={data.today}
                           onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
                  </label>
                  <label style={S.label}>To
                    <input type="date" value={form.end_date} min={form.start_date || data.today}
                           onChange={(e) => setForm({ ...form, end_date: e.target.value })} />
                  </label>
                </div>
                <label style={{ ...S.label, marginTop: 10 }}>Reason
                  <input type="text" placeholder="Lakshmi.R on medical leave" maxLength={255}
                         value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} />
                </label>
              </>
            ) : (
              <>
                <p style={{ fontSize: 14, color: "#374151" }}>
                  <b>{dialog.a.teacher.username}</b> · {dialog.a.department.name} · {fmtD(dialog.a.start_date)} to {fmtD(dialog.a.end_date)}
                  {dialog.a.nominated_by && <> · nominated by {dialog.a.nominated_by}</>}
                </p>
                {dialog.kind === "approve" && (
                  <p style={{ fontSize: 14, background: TONE.violet.bg, color: VIOLET, border: `1px solid ${TONE.violet.bd}`, borderRadius: 8, padding: "8px 10px" }}>
                    {dialog.a.teacher.username} gets the HOD powers of {dialog.a.department.name}{" "}
                    {data.today >= dialog.a.start_date ? "from now" : `from ${fmtD(dialog.a.start_date)}`} until {fmtD(dialog.a.end_date)}.{" "}
                    {regularHod(dialog.a.department.id)} stays a teacher in that time.
                  </p>
                )}
                {dialog.kind === "end" && (
                  <p style={{ fontSize: 14, background: "#fff7ed", color: "#c2410c", border: "1px solid #fed7aa", borderRadius: 8, padding: "8px 10px" }}>
                    {dialog.a.status === "upcoming"
                      ? "This assignment will not start."
                      : `${dialog.a.teacher.username}'s HOD powers stop immediately. ${regularHod(dialog.a.department.id)} becomes HOD again.`}
                  </p>
                )}
                {dialog.kind === "extend" && (
                  <label style={{ ...S.label, marginBottom: 10 }}>New end date
                    <input type="date" value={dlgEnd} min={dialog.a.end_date} onChange={(e) => setDlgEnd(e.target.value)} />
                  </label>
                )}
                {["extend", "end", "reject"].includes(dialog.kind) && (
                  <label style={S.label}>Reason (required)
                    <textarea rows={3} maxLength={255} value={dlgReason} placeholder="At least 10 characters"
                              onChange={(e) => setDlgReason(e.target.value)} />
                  </label>
                )}
              </>
            )}

            {dlgErr && <p style={{ color: "#b91c1c", fontSize: 14, fontWeight: 600 }}>{dlgErr}</p>}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 16 }}>
              <button className="btn-edit" onClick={() => setDialog(null)} disabled={busy}>Close</button>
              <button className={["end", "reject"].includes(dialog.kind) ? "btn-delete" : "btn-primary"}
                      style={{ padding: "6px 16px", borderRadius: 6 }} onClick={submitDialog} disabled={busy}>
                {dlgButton[dialog.kind]}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}