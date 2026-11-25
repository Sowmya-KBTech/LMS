// ============================================================
// AUTOMATION SCREEN (Point 12, step 8) — Admin › Automation
// ============================================================
// Settings for the nightly reminder jobs, the job diary (last runs) and a
// "Preview tonight" dry run that shows who WOULD be notified, sending nothing.
// Main admin only (the APIs refuse everyone else).
// ============================================================
import { useEffect, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";
import API from "../../api";
import "../../App.css";
import "../../styles/Attendance.css";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const FIELDS = ["fee_reminders_on", "fee_remind_days_before", "fee_grace_days",
  "attendance_alerts_on", "attendance_alert_weekday"];

const fmtWhen = (iso) =>
  iso
    ? new Date(iso).toLocaleString("en-IN", {
        day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
      })
    : "—";

const STATUS_STYLE = {
  ok: { background: "#ecfdf5", color: "#15803d" },
  failed: { background: "#fef2f2", color: "#B42318" },
  running: { background: "#f5f2ff", color: "#4B32C3" },
  skipped: { background: "#F4F4F6", color: "#5D5A6B" },
  warning: { background: "#fffbeb", color: "#B45309" },
  problem: { background: "#fef2f2", color: "#B42318" },
  unknown: { background: "#F4F4F6", color: "#5D5A6B" },
};

export default function AutomationAdmin() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);       // settings from the server
  const [form, setForm] = useState(null);       // what the admin is editing
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState({ tone: "", text: "" });
  const [runs, setRuns] = useState([]);
  const [health, setHealth] = useState(null);   // Redis/Celery work, step 8.4: is Beat / the worker alive?
  const [preview, setPreview] = useState("");
  const [previewing, setPreviewing] = useState(false);

  const loadSettings = () =>
    API.get("automation/settings/")
      .then((r) => {
        setData(r.data);
        const f = {};
        FIELDS.forEach((k) => { f[k] = r.data[k]; });
        setForm(f);
      })
      .catch((err) => setError(err?.response?.data?.detail || "Could not load the automation settings."));

  const loadRuns = () =>
    API.get("automation/runs/").then((r) => setRuns(r.data || [])).catch(() => setRuns([]));

  const loadHealth = () =>
    API.get("automation/health/").then((r) => setHealth(r.data)).catch(() => setHealth(null));

  useEffect(() => {
    loadSettings();
    loadRuns();
    loadHealth();
  }, []);

  const changed = data && form && FIELDS.some((k) => String(form[k]) !== String(data[k]));

  const save = async () => {
    setSaving(true);
    setMsg({ tone: "", text: "" });
    try {
      const r = await API.put("automation/settings/", {
        ...form,
        fee_remind_days_before: Number(form.fee_remind_days_before),
        fee_grace_days: Number(form.fee_grace_days),
        attendance_alert_weekday: Number(form.attendance_alert_weekday),
      });
      setData(r.data);
      setMsg({ tone: "ok", text: "✓ Saved. Tonight's run uses these settings." });
    } catch (err) {
      setMsg({ tone: "bad", text: err?.response?.data?.detail || "Could not save." });
    } finally {
      setSaving(false);
    }
  };

  const runPreview = async () => {
    setPreviewing(true);
    setPreview("");
    try {
      const r = await API.post("automation/preview/");
      setPreview(r.data?.output || "(no output)");
      loadRuns();
    } catch (err) {
      setPreview(err?.response?.data?.detail || "Could not run the preview.");
    } finally {
      setPreviewing(false);
    }
  };

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">
            <div className="att-page" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <div>
                <h1 style={{ margin: 0 }}>Automation</h1>
                <p style={{ margin: "6px 0 0", color: "#5D5A6B", fontSize: 15 }}>
                  Reminders the LMS sends by itself every night at 12:15 AM — fees, low attendance and
                  assignments — then emails them through the queue.
                </p>
              </div>

              {error && <div className="att-card"><p style={{ color: "#B42318", margin: 0 }}>{error}</p></div>}

              {/* ===== SYSTEM HEALTH (Redis/Celery work, step 8.4) ===== */}
              {health && (
                <div className="att-card">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <h2 className="att-card-title" style={{ margin: 0 }}>
                      System health{" "}
                      <span style={{ ...(STATUS_STYLE[health.overall] || STATUS_STYLE.unknown), fontSize: 13, fontWeight: 700, borderRadius: 999, padding: "2px 10px", marginLeft: 6 }}>
                        {health.overall.toUpperCase()}
                      </span>
                    </h2>
                    <button className="att-btn-outline" onClick={loadHealth} style={{ padding: "5px 12px", fontSize: 13.5 }}>Check again</button>
                  </div>
                  <div className="att-table-wrap" style={{ marginTop: 12 }}>
                    <table className="att-table">
                      <tbody>
                        {health.checks.map((c) => (
                          <tr key={c.name}>
                            <td className="att-td-name" style={{ whiteSpace: "nowrap" }}>{c.name}</td>
                            <td className="center" style={{ width: 110 }}>
                              <span style={{ ...(STATUS_STYLE[c.status] || STATUS_STYLE.unknown), fontSize: 13, fontWeight: 700, borderRadius: 999, padding: "2px 10px" }}>
                                {c.status.toUpperCase()}
                              </span>
                            </td>
                            <td style={{ whiteSpace: "normal", fontSize: 14 }}>{c.detail}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p style={{ margin: "8px 0 0", color: "#85839A", fontSize: 13 }}>Checked {fmtWhen(health.checked_at)}</p>
                </div>
              )}

              {/* ===== SETTINGS ===== */}
              {form && (
                <div className="att-card">
                  <h2 className="att-card-title">Settings</h2>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 18 }}>
                    <div style={{ border: "1px solid #E7E7EC", borderRadius: 12, padding: 14 }}>
                      <label style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 600, fontSize: 15.5, marginBottom: 12 }}>
                        <input type="checkbox" checked={form.fee_reminders_on}
                          onChange={(e) => set("fee_reminders_on", e.target.checked)} style={{ width: 18, height: 18 }} />
                        Fee reminders
                      </label>
                      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                        <div className="att-field">
                          <label className="att-label" htmlFor="au-before">Remind before due date</label>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <input id="au-before" className="att-input" type="number" min={1} max={30} style={{ width: 80 }}
                              value={form.fee_remind_days_before} disabled={!form.fee_reminders_on}
                              onChange={(e) => set("fee_remind_days_before", e.target.value)} />
                            <span style={{ fontSize: 15 }}>days</span>
                          </div>
                        </div>
                        <div className="att-field">
                          <label className="att-label" htmlFor="au-grace">Grace period after due date</label>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <input id="au-grace" className="att-input" type="number" min={0} max={60} style={{ width: 80 }}
                              value={form.fee_grace_days} disabled={!form.fee_reminders_on}
                              onChange={(e) => set("fee_grace_days", e.target.value)} />
                            <span style={{ fontSize: 15 }}>days</span>
                          </div>
                        </div>
                      </div>
                      <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "#85839A" }}>
                        Student and parents: due soon, overdue (inside grace), grace ended (+ accounts admin).
                      </p>
                    </div>

                    <div style={{ border: "1px solid #E7E7EC", borderRadius: 12, padding: 14 }}>
                      <label style={{ display: "flex", alignItems: "center", gap: 10, fontWeight: 600, fontSize: 15.5, marginBottom: 12 }}>
                        <input type="checkbox" checked={form.attendance_alerts_on}
                          onChange={(e) => set("attendance_alerts_on", e.target.checked)} style={{ width: 18, height: 18 }} />
                        Weekly low-attendance alert
                      </label>
                      <div className="att-field">
                        <label className="att-label" htmlFor="au-day">Send on</label>
                        <select id="au-day" className="att-input" style={{ width: 160 }}
                          value={form.attendance_alert_weekday} disabled={!form.attendance_alerts_on}
                          onChange={(e) => set("attendance_alert_weekday", e.target.value)}>
                          {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                        </select>
                      </div>
                      <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "#85839A" }}>
                        Students below the minimum in Results › Hall Ticket › Eligibility rules, their parents,
                        and one list to each class in-charge.
                      </p>
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 16, flexWrap: "wrap" }}>
                    <button className="att-save-btn" onClick={save} disabled={!changed || saving}
                      style={{ opacity: !changed || saving ? 0.5 : 1 }}>
                      {saving ? "Saving…" : "Save settings"}
                    </button>
                    {msg.text && (
                      <span role="status" style={{ fontSize: 14.5, fontWeight: 600, color: msg.tone === "ok" ? "#15803d" : "#B42318" }}>
                        {msg.text}
                      </span>
                    )}
                    {data?.updated_by && (
                      <span style={{ fontSize: 13.5, color: "#85839A" }}>
                        Last changed by {data.updated_by} on {fmtWhen(data.updated_at)}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* ===== SCHEDULE + PREVIEW ===== */}
              {data && (
                <div className="att-card">
                  <h2 className="att-card-title">Tonight&apos;s jobs</h2>
                  <p style={{ margin: "0 0 12px", fontSize: 14.5, color: "#5D5A6B" }}>
                    Run in this order by <code>run_daily_jobs.bat</code> (Windows Task Scheduler, 12:15 AM).
                    Results are emailed when you publish them; that one is not on the nightly list.
                  </p>
                  <div className="att-table-wrap">
                    <table className="att-table">
                      <thead><tr><th>#</th><th>Job</th><th>When</th></tr></thead>
                      <tbody>
                        {data.jobs.map((j, i) => (
                          <tr key={j.name}>
                            <td>{i + 1}</td>
                            <td className="att-td-name">{j.label}</td>
                            <td>{j.when}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 14 }}>
                    <button className="att-btn-outline" onClick={runPreview} disabled={previewing}>
                      {previewing ? "Checking…" : "Preview tonight (dry run)"}
                    </button>
                    <span style={{ fontSize: 13.5, color: "#85839A" }}>Shows who would be notified. Sends nothing.</span>
                  </div>
                  {preview && (
                    <pre style={{
                      marginTop: 12, background: "#F7F7F9", border: "1px solid #E7E7EC", borderRadius: 10,
                      padding: "12px 14px", fontSize: 13.5, lineHeight: 1.55, whiteSpace: "pre-wrap", maxHeight: 360, overflow: "auto",
                    }}>{preview}</pre>
                  )}
                </div>
              )}

              {/* ===== LAST RUNS (job diary) ===== */}
              {data && (
                <div className="att-card">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
                    <h2 className="att-card-title" style={{ margin: 0 }}>Last runs</h2>
                    <button className="att-btn-outline" onClick={loadRuns} style={{ padding: "5px 12px", fontSize: 13.5 }}>Refresh</button>
                  </div>
                  {runs.length === 0 ? (
                    <div className="att-state"><p>No runs yet.</p></div>
                  ) : (
                    <div className="att-table-wrap" style={{ marginTop: 12 }}>
                      <table className="att-table">
                        <thead>
                          <tr><th>Started</th><th>Job</th><th className="center">Status</th><th className="center">Sent</th><th>Mode</th><th>Error</th></tr>
                        </thead>
                        <tbody>
                          {runs.map((r) => (
                            <tr key={r.id}>
                              <td style={{ whiteSpace: "nowrap" }}>{fmtWhen(r.started_at)}</td>
                              <td className="att-td-name">{r.label}</td>
                              <td className="center">
                                <span style={{ ...(STATUS_STYLE[r.status] || STATUS_STYLE.skipped), fontSize: 13, fontWeight: 700, borderRadius: 999, padding: "2px 10px" }}>
                                  {r.status.toUpperCase()}
                                </span>
                              </td>
                              <td className="center">{r.sent_count}</td>
                              <td style={{ color: r.dry_run ? "#85839A" : "#17151F" }}>{r.dry_run ? "Dry run" : "Real"}</td>
                              <td style={{ maxWidth: 280, whiteSpace: "normal", color: "#B42318", fontSize: 13.5 }}>{r.message}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
