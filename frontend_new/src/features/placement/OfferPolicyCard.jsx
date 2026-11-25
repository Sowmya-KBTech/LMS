// College-wide placement rules (checked by the backend's eligibility for
// every role, on top of each company's own CGPA / arrears rules):
//   * Final-year students only (from each student's course)
//   * A student with an ACCEPTED offer may apply only to roles paying the
//     same or more (offers not yet accepted don't count)
//   * Optional Dream / Super dream tiers
import { useEffect, useState } from "react";
import API from "../../api";

export default function OfferPolicyCard() {
  const [p, setP] = useState(null);
  const [form, setForm] = useState({
    final_year_only: true, higher_package_only: true,
    tiers_enabled: false, dream_min_lpa: "", super_dream_min_lpa: "",
  });
  const [msg, setMsg] = useState({ ok: "", err: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    API.get("placement/policy/")
      .then((r) => {
        setP(r.data);
        setForm({
          final_year_only: r.data.final_year_only ?? true,
          higher_package_only: r.data.higher_package_only ?? true,
          tiers_enabled: r.data.tiers_enabled,
          dream_min_lpa: r.data.dream_min_lpa ?? "",
          super_dream_min_lpa: r.data.super_dream_min_lpa ?? "",
        });
      })
      .catch(() => setMsg({ ok: "", err: "Could not load the offer policy." }));
  }, []);

  const save = async (e) => {
    e.preventDefault();
    setMsg({ ok: "", err: "" });
    try {
      setBusy(true);
      const r = await API.put("placement/policy/", form);
      setP(r.data);
      setMsg({ ok: "Placement rules saved.", err: "" });
    } catch (err) {
      setMsg({ ok: "", err: err.response?.data?.detail || "Could not save." });
    } finally {
      setBusy(false);
    }
  };

  if (!p) return msg.err ? <div className="card">{msg.err}</div> : null;
  const edit = p.can_edit;

  return (
    <div className="card">
      <h3>Placement rules</h3>
      <p className="pl-hint">
        These apply to every drive, on top of each company's own CGPA / arrears rules.
        A role with no company rules is open to every student these rules allow.
      </p>
      <form className="pl-policy" onSubmit={save}>
        <label className="pl-check pl-check--row">
          <input
            type="checkbox"
            checked={form.final_year_only}
            disabled={!edit}
            onChange={(e) => setForm({ ...form, final_year_only: e.target.checked })}
          />
          Final-year students only
        </label>
        <label className="pl-check pl-check--row">
          <input
            type="checkbox"
            checked={form.higher_package_only}
            disabled={!edit}
            onChange={(e) => setForm({ ...form, higher_package_only: e.target.checked })}
          />
          Placed students can apply only to the same or a higher package
        </label>
        <p className="pl-hint pl-policy-note">
          "Placed" means an accepted offer. Example: accepted 4 LPA → 4 LPA and above are open, 3.5 LPA is not.
        </p>
        <label className="pl-check">
          <input
            type="checkbox"
            checked={form.tiers_enabled}
            disabled={!edit}
            onChange={(e) => setForm({ ...form, tiers_enabled: e.target.checked })}
          />
          Also use Dream / Super dream tiers (optional)
        </label>
        <label>
          Dream from (LPA)
          <input
            type="number" min="0" step="0.1" disabled={!edit}
            value={form.dream_min_lpa}
            onChange={(e) => setForm({ ...form, dream_min_lpa: e.target.value })}
            placeholder="e.g. 6"
          />
        </label>
        <label>
          Super dream from (LPA)
          <input
            type="number" min="0" step="0.1" disabled={!edit}
            value={form.super_dream_min_lpa}
            onChange={(e) => setForm({ ...form, super_dream_min_lpa: e.target.value })}
            placeholder="e.g. 10"
          />
        </label>
        {edit && <button className="btn-primary" type="submit" disabled={busy}>Save rules</button>}
      </form>
      {msg.ok && <p className="pl-ok">{msg.ok}</p>}
      {msg.err && <p className="pl-err">{msg.err}</p>}
    </div>
  );
}
