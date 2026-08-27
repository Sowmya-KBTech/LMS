// frontend/src/features/mentoring/HodMentoringSettings.jsx
import { useCallback, useEffect, useState } from "react";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import MentoringTabs from "./MentoringTabs";

import { errorText, getSettings, saveSettings } from "./mentoringApi";

import "../../App.css";
import "../../styles/MentorAllocation.css";

export default function HodMentoringSettings() {
  const [open, setOpen] = useState(false);

  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  const flash = (m) => {
    setToast(m);
    setTimeout(() => setToast(""), 3000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setForm(await getSettings());
    } catch (err) {
      setError(errorText(err, "Could not load settings. Are you an HOD?"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const set = (k, v) => setForm((p) => ({ ...p, [k]: v }));

  const save = async () => {
    // A must sit above B, or every student lands in one grade.
    if (Number(form.band_a_min) <= Number(form.band_b_min)) {
      flash("Grade A threshold must be higher than grade B.");
      return;
    }
    setSaving(true);
    try {
      const d = await saveSettings({
        max_students_per_mentor: Number(form.max_students_per_mentor),
        band_a_min: Number(form.band_a_min),
        band_b_min: Number(form.band_b_min),
        require_all_bands: form.require_all_bands,
        route_via_advisor: form.route_via_advisor,
        first_year_rule: form.first_year_rule,
      });
      setForm(d);
      flash("Settings saved");
    } catch (err) {
      flash(errorText(err, "Could not save."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            <div className="header-box">
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <h2 style={{ margin: 0 }}>Allocation Settings</h2>
                {form?.department_name && (
                  <span className="ma-pill ma-blue">{form.department_name}</span>
                )}
              </div>
              <p>Grade thresholds, capacity and the composition rule</p>
            </div>

            <MentoringTabs />

            {error && (
              <div className="ma-note red" style={{ marginBottom: 16 }}>
                <b>Could not load</b>{error}
              </div>
            )}

            {loading && (
              <div className="ma-panel"><div className="ma-empty">Loading…</div></div>
            )}

            {!loading && form && (
              <>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>

                  {/* ================= GRADE THRESHOLDS ================= */}
                  <div className="ma-panel">
                    <div className="ma-panel-head">
                      <div>
                        <h3>Grade thresholds</h3>
                        <p>Computed from published semester results, on a 10-point scale</p>
                      </div>
                    </div>
                    <div className="ma-panel-body">
                      <div style={{ marginBottom: 15 }}>
                        <span className="ma-label">Grade A from</span>
                        <input
                          type="number" step="0.1" min="0" max="10"
                          value={form.band_a_min}
                          onChange={(e) => set("band_a_min", e.target.value)}
                          style={{ padding: "9px 11px", border: "1px solid #e6e9ef", borderRadius: 9, width: 110 }}
                        />
                        <span style={{ marginLeft: 8, fontSize: 12.5, color: "#6b7280" }}>
                          and above
                        </span>
                      </div>
                      <div style={{ marginBottom: 15 }}>
                        <span className="ma-label">Grade B from</span>
                        <input
                          type="number" step="0.1" min="0" max="10"
                          value={form.band_b_min}
                          onChange={(e) => set("band_b_min", e.target.value)}
                          style={{ padding: "9px 11px", border: "1px solid #e6e9ef", borderRadius: 9, width: 110 }}
                        />
                        <span style={{ marginLeft: 8, fontSize: 12.5, color: "#6b7280" }}>
                          up to {(Number(form.band_a_min) - 0.01).toFixed(2)}
                        </span>
                      </div>
                      <div className="ma-note">
                        <b>Grade C</b>
                        Anything below {form.band_b_min}. There is no separate setting —
                        it is whatever the other two leave behind.
                      </div>

                      <div style={{ marginTop: 15 }}>
                        <span className="ma-label">First-year students</span>
                        <select
                          value={form.first_year_rule}
                          onChange={(e) => set("first_year_rule", e.target.value)}
                          style={{ padding: "9px 11px", border: "1px solid #e6e9ef", borderRadius: 9, width: "100%" }}
                        >
                          <option value="defer">Allocate only after semester 1 results</option>
                          <option value="band_b">Assign all first years grade B</option>
                        </select>
                        <div className="ma-note amber" style={{ marginTop: 9 }}>
                          <b>First years have no published result</b>
                          There is no CGPA to compute a grade from, so this rule decides
                          what happens to them.
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* ================= ALLOCATION RULES ================= */}
                  <div className="ma-panel">
                    <div className="ma-panel-head"><div><h3>Allocation rules</h3></div></div>
                    <div className="ma-panel-body">
                      <div style={{ marginBottom: 15 }}>
                        <span className="ma-label">Maximum students per mentor</span>
                        <input
                          type="number" min="1" max="200"
                          value={form.max_students_per_mentor}
                          onChange={(e) => set("max_students_per_mentor", e.target.value)}
                          style={{ padding: "9px 11px", border: "1px solid #e6e9ef", borderRadius: 9, width: 110 }}
                        />
                        <div style={{ fontSize: 11.5, color: "#6b7280", marginTop: 5 }}>
                          Exceeding it shows a warning on the allocation bar. It never
                          blocks the assignment.
                        </div>
                      </div>

                      <div style={{ marginBottom: 15 }}>
                        <label style={{ display: "flex", gap: 9, alignItems: "flex-start", fontSize: 13, cursor: "pointer" }}>
                          <input
                            type="checkbox"
                            checked={form.require_all_bands}
                            onChange={(e) => set("require_all_bands", e.target.checked)}
                            style={{ marginTop: 3 }}
                          />
                          <span>
                            <b>Every group must contain grade A, B and C students</b>
                            <br />
                            <span style={{ fontSize: 11.5, color: "#6b7280" }}>
                              The Anna University composition rule. Turning this off
                              removes the balance checks everywhere.
                            </span>
                          </span>
                        </label>
                      </div>

                      <div style={{ marginBottom: 15 }}>
                        <label style={{ display: "flex", gap: 9, alignItems: "flex-start", fontSize: 13, cursor: "pointer" }}>
                          <input
                            type="checkbox"
                            checked={form.route_via_advisor}
                            onChange={(e) => set("route_via_advisor", e.target.checked)}
                            style={{ marginTop: 3 }}
                          />
                          <span>
                            <b>Class advisor proposes, HOD approves</b>
                            <br />
                            <span style={{ fontSize: 11.5, color: "#6b7280" }}>
                              Off means you allocate directly, with no proposal step.
                            </span>
                          </span>
                        </label>
                      </div>

                      <button className="ma-btn primary" onClick={save} disabled={saving}>
                        {saving ? "Saving…" : "Save settings"}
                      </button>
                      <button className="ma-btn" onClick={load} style={{ marginLeft: 8 }}>
                        Cancel
                      </button>
                    </div>
                  </div>
                </div>

                {/* ================= VISIBILITY ================= */}
                <div className="ma-panel" style={{ marginTop: 16 }}>
                  <div className="ma-panel-head">
                    <div>
                      <h3>Who can see the grade</h3>
                      <p>An internal planning value, not a label for students</p>
                    </div>
                  </div>
                  <div className="ma-scroll">
                    <table className="ma-table">
                      <thead>
                        <tr><th>Role</th><th>Sees the grade</th><th>Reason</th></tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td><b>HOD</b></td>
                          <td><span className="ma-pill ma-green">Yes</span></td>
                          <td style={{ fontSize: 12, color: "#6b7280" }}>Needs it to form balanced groups</td>
                        </tr>
                        <tr>
                          <td><b>Mentor</b></td>
                          <td><span className="ma-pill ma-green">Yes</span></td>
                          <td style={{ fontSize: 12, color: "#6b7280" }}>Their own group only</td>
                        </tr>
                        <tr>
                          <td><b>Student</b></td>
                          <td><span className="ma-pill ma-red">No</span></td>
                          <td style={{ fontSize: 12, color: "#6b7280" }}>
                            A visible A/B/C label on a person spreads between classmates
                          </td>
                        </tr>
                        <tr>
                          <td><b>Parent</b></td>
                          <td><span className="ma-pill ma-red">No</span></td>
                          <td style={{ fontSize: 12, color: "#6b7280" }}>Same reason</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div className="ma-panel-foot">
                    This is enforced in the API, not just hidden in the UI — the student
                    endpoint never sends the grade field.
                  </div>
                </div>
              </>
            )}

          </div>
        </div>
      </div>
      {toast && <div className="ma-toast">{toast}</div>}
    </div>
  );
}