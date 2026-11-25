// frontend/src/features/mentoring/HodMentoringSettings.jsx
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import Navbar from "../../components/Navbar";
import Sidebar from "../../components/Sidebar";
import MentoringTabs from "./MentoringTabs";

import { errorText, getSettings, saveSettings } from "./mentoringApi";

import "../../App.css";
import "../../styles/MentorAllocation.css";

export default function HodMentoringSettings() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

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
      setForm(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    if (Number(form.band_b_min) >= Number(form.band_a_min)) {
      flash("Grade B has to start below grade A.");
      return;
    }
    setSaving(true);
    try {
      // require_all_bands is deliberately not sent. It is read-only on the
      // server now, derived from MentorRule.grade_mix, and DRF drops read-only
      // fields without complaint — so sending it would look like it worked.
      const {
        max_students_per_mentor,
        allocate_from_year,
        band_a_min,
        band_b_min,
        route_via_advisor,
        first_year_rule,
      } = form;

      const saved = await saveSettings({
        max_students_per_mentor,
        allocate_from_year,
        band_a_min,
        band_b_min,
        route_via_advisor,
        first_year_rule,
      });
      setForm(saved);
      flash("Saved. New allocations use these settings.");
    } catch (err) {
      flash(errorText(err, "Could not save."));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="app">
        <Navbar setOpen={setOpen} />
        <div className="layout">
          <Sidebar open={open} setOpen={setOpen} />
          <div className="main">
            <div className="content">
              <div className="ma-panel"><div className="ma-empty">Loading…</div></div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !form) {
    return (
      <div className="app">
        <Navbar setOpen={setOpen} />
        <div className="layout">
          <Sidebar open={open} setOpen={setOpen} />
          <div className="main">
            <div className="content">
              <div className="ma-note red"><b>Could not load</b>{error}</div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <Navbar setOpen={setOpen} />
      <div className="layout">
        <Sidebar open={open} setOpen={setOpen} />
        <div className="main">
          <div className="content">

            <div className="header-box">
              <h2>Mentoring Settings</h2>
              <p>
                {form.department_name} · applies to allocations made from now on,
                not to ones already approved
              </p>
            </div>

            <MentoringTabs />

            {/* ms-form scopes this page's form layout.
                MentorAllocation.css is imported AFTER App.css and defines its
                own .ma-label / .ma-field, so page rules written as bare class
                selectors lost to it and the fields overlapped. Every rule is
                written as ".ms-form .ma-field" - two classes beats one on
                specificity, so import order stops mattering. */}
            <div className="ma-two ms-form">
              {/* ---------------- grade thresholds ---------------- */}
              <div className="ma-panel">
                <div className="ma-panel-head">
                  <div>
                    <h3>Grade thresholds</h3>
                    <p>Computed from published semester results, on a 10-point scale</p>
                  </div>
                </div>
                <div className="ma-panel-body">
                  <div className="ma-field">
                    <label className="ma-label" htmlFor="band_a_min">Grade A from</label>
                    <div className="ma-inline">
                      <input
                        id="band_a_min"
                        className="ma-input narrow"
                        type="number" step="0.1" min="0" max="10"
                        value={form.band_a_min}
                        onChange={(e) => set("band_a_min", e.target.value)}
                      />
                      <span className="ma-suffix">and above</span>
                    </div>
                  </div>

                  <div className="ma-field">
                    <label className="ma-label" htmlFor="band_b_min">Grade B from</label>
                    <div className="ma-inline">
                      <input
                        id="band_b_min"
                        className="ma-input narrow"
                        type="number" step="0.1" min="0" max="10"
                        value={form.band_b_min}
                        onChange={(e) => set("band_b_min", e.target.value)}
                      />
                      <span className="ma-suffix">
                        up to {(Number(form.band_a_min) - 0.01).toFixed(2)}
                      </span>
                    </div>
                  </div>

                  <div className="ma-note">
                    <b>Grade C</b>
                    Anything below {form.band_b_min}. There is no separate setting —
                    it is whatever the other two leave behind.
                  </div>

                  <div className="ma-field">
                    <label className="ma-label" htmlFor="first_year_rule">
                      First-year students
                    </label>
                    <select
                      id="first_year_rule"
                      className="ma-input"
                      value={form.first_year_rule}
                      onChange={(e) => set("first_year_rule", e.target.value)}
                    >
                      <option value="defer">Allocate only after semester 1 results</option>
                      <option value="band_b">Assign all first years band B</option>
                    </select>
                  </div>

                  <div className="ma-note amber">
                    <b>First years have no published result</b>
                    There is no CGPA to compute a grade from, so this rule decides what
                    happens to them.
                    {form.allocate_from_year > 1 && (
                      <>
                        {" "}It has no effect while allocation starts from year{" "}
                        {form.allocate_from_year}.
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* ---------------- allocation rules ---------------- */}
              <div className="ma-panel">
                <div className="ma-panel-head">
                  <div>
                    <h3>Allocation rules</h3>
                    <p>Who gets allocated, and how it is approved</p>
                  </div>
                </div>
                <div className="ma-panel-body">
                  <div className="ma-field">
                    <label className="ma-label" htmlFor="allocate_from_year">
                      Start allocating from
                    </label>
                    <select
                      id="allocate_from_year"
                      className="ma-input"
                      value={form.allocate_from_year}
                      onChange={(e) => set("allocate_from_year", Number(e.target.value))}
                    >
                      <option value={1}>I Year onwards</option>
                      <option value={2}>II Year onwards</option>
                      <option value={3}>III Year onwards</option>
                      <option value={4}>IV Year only</option>
                    </select>
                    <span className="ma-hint">
                      Students below this year do not appear on the allocation screens
                      at all.
                    </span>
                  </div>

                  <div className="ma-field">
                    <label className="ma-label" htmlFor="max_students_per_mentor">
                      Maximum students per mentor
                    </label>
                    <input
                      id="max_students_per_mentor"
                      className="ma-input narrow"
                      type="number" min="1" max="200"
                      value={form.max_students_per_mentor}
                      onChange={(e) => set("max_students_per_mentor", e.target.value)}
                    />
                    <span className="ma-hint">
                      Exceeding it shows a warning on the allocation bar. It never
                      blocks the assignment.
                    </span>
                  </div>

                  {/* Read-only. This used to be a checkbox saved here, while team
                      formation read MentorRule.grade_mix — two settings for one
                      policy, and nothing kept them in step. A HOD could turn it
                      off, get "Saved", and watch teams carry on enforcing it. The
                      rule is the single source of truth now.

                      The button goes to Team Proposals, which is where grade_mix
                      is actually edited. It used to point at /hod/mentor-allocation,
                      a screen that does not hold this setting. */}
                  <div className="ma-field">
                    <span className="ma-label">Group composition</span>
                    <div className="ma-readonly">
                      <span
                        className={`ma-pill ${form.require_all_bands ? "ma-green" : "ma-grey"}`}
                      >
                        {form.require_all_bands ? "A, B and C required" : "No grade rule"}
                      </span>
                      <div className="ma-readonly-body">
                        {form.require_all_bands
                          ? "Every mentor group must hold a grade A, a grade B and a grade C student."
                          : "Groups can hold any mix of grades."}
                        <span className="ma-hint">
                          Set per academic year on the Team Proposals screen, because
                          team formation and direct allocation both read it there.
                        </span>
                      </div>
                    </div>
                    <button
                      className="ma-btn small ma-field-btn"
                      onClick={() => navigate("/hod/team-proposals")}
                    >
                      Change the composition rule
                    </button>
                  </div>

                  <label className="ma-check-row">
                    <input
                      type="checkbox"
                      checked={form.route_via_advisor}
                      onChange={(e) => set("route_via_advisor", e.target.checked)}
                    />
                    <span className="ma-check-text">
                      <b>Class in-charge proposes, HOD approves</b>
                      <span className="ma-hint">
                        Off means you allocate directly, with no proposal step.
                      </span>
                    </span>
                  </label>

                  <div className="ma-actions ma-form-actions">
                    <button className="ma-btn primary" disabled={saving} onClick={submit}>
                      {saving ? "Saving…" : "Save settings"}
                    </button>
                    <button className="ma-btn" disabled={saving} onClick={load}>
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>
      {toast && <div className="ma-toast">{toast}</div>}
    </div>
  );
}