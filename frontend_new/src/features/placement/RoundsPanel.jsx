// ============================================================
// RoundsPanel — record who cleared each selection round of a role
// ============================================================
// The company runs the tests; the placement office records the shortlist
// it sends back. Round 1 lists everyone who applied, each later round
// lists only those who cleared the round before (worked out by the API).
// ============================================================
import { useEffect, useState } from "react";
import API from "../../api";
import ImportExport from "../../components/ImportExport";

const TYPES = [
  ["aptitude", "Online / aptitude test"],
  ["gd", "Group discussion"],
  ["technical", "Technical interview"],
  ["hr", "HR interview"],
  ["other", "Other"],
];

const STATUS_LABEL = { cleared: "Cleared", not_cleared: "Not cleared", absent: "Absent" };

export default function RoundsPanel({ role }) {
  const [info, setInfo] = useState(null);       // role rounds summary
  const [roundId, setRoundId] = useState(null); // selected round
  const [sheet, setSheet] = useState(null);     // that round's students
  const [form, setForm] = useState({ round_type: "aptitude", name: "", round_date: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadRounds = (keep) =>
    API.get(`placement/roles/${role.id}/rounds/`)
      .then((r) => {
        setInfo(r.data);
        const ids = r.data.rounds.map((x) => x.id);
        const next = keep && ids.includes(keep) ? keep : ids[0] || null;
        setRoundId(next);
        return next;
      })
      .catch(() => setError("Could not load rounds."));

  const loadSheet = (id) => {
    if (!id) { setSheet(null); return Promise.resolve(); }
    return API.get(`placement/rounds/${id}/results/`)
      .then((r) => setSheet(r.data))
      .catch(() => setError("Could not load this round."));
  };

  useEffect(() => {
    setInfo(null); setSheet(null); setError("");
    loadRounds().then((id) => loadSheet(id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role.id]);

  const pick = (id) => { setRoundId(id); loadSheet(id); };

  const refresh = async (id = roundId) => {
    await loadRounds(id);
    await loadSheet(id);
  };

  const addRound = async (e) => {
    e.preventDefault();
    setError("");
    try {
      setBusy(true);
      const r = await API.post(`placement/roles/${role.id}/rounds/`, {
        ...form, round_date: form.round_date || null,
      });
      setForm({ round_type: "aptitude", name: "", round_date: "" });
      await refresh(r.data.id);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not add the round.");
    } finally {
      setBusy(false);
    }
  };

  const removeRound = async (rd) => {
    if (!window.confirm(`Delete "${rd.name}" and its results?`)) return;
    try {
      setBusy(true);
      await API.delete(`placement/rounds/${rd.id}/`);
      await refresh(null);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not delete the round.");
    } finally {
      setBusy(false);
    }
  };

  const mark = async (results) => {
    setError("");
    try {
      setBusy(true);
      await API.post(`placement/rounds/${roundId}/results/`, { results });
      await refresh(roundId);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not save.");
    } finally {
      setBusy(false);
    }
  };

  const markRest = () => {
    const rest = (sheet?.results || []).filter((r) => !r.status);
    if (rest.length === 0) return;
    if (!window.confirm(`Mark the ${rest.length} unmarked student(s) as Not cleared?`)) return;
    mark(rest.map((r) => ({ application: r.application, status: "not_cleared" })));
  };

  if (!info) return <div className="card">{error || "Loading rounds…"}</div>;

  const rounds = info.rounds;
  const current = rounds.find((r) => r.id === roundId);
  const c = sheet?.counts || {};

  return (
    <>
      {error && (
        <div className="card" style={{ borderLeft: "4px solid #dc2626", color: "#991b1b" }}>{error}</div>
      )}

      <div className="card">
        <h3>Selection rounds</h3>
        <p className="pl-hint">
          Optional. Add the company's rounds and mark who cleared each one from the
          shortlist they send. Students see their progress on their placement page.
        </p>

        {rounds.length > 0 ? (
          <div className="pl-round-tabs" role="tablist">
            {rounds.map((rd, i) => (
              <button
                key={rd.id}
                type="button"
                role="tab"
                aria-selected={rd.id === roundId}
                className={`pl-round-tab${rd.id === roundId ? " active" : ""}`}
                onClick={() => pick(rd.id)}
              >
                <span className="pl-round-no">{i + 1}</span>
                <span>
                  <strong>{rd.name}</strong>
                  <small>
                    {rd.counts.cleared}/{rd.counts.in_round} cleared
                    {rd.round_date ? ` · ${rd.round_date}` : ""}
                  </small>
                </span>
              </button>
            ))}
          </div>
        ) : (
          <p className="pl-hint">No rounds yet — this role goes straight from attendance to offers.</p>
        )}

        {info.selected_count !== null && rounds.length > 0 && (
          <p className="pl-selected">
            Selected (cleared the last round): <strong>{info.selected_count}</strong>
          </p>
        )}

        {info.can_manage && (
          <form className="form-grid form-grid--row pl-add-round" onSubmit={addRound}>
            <select
              value={form.round_type}
              onChange={(e) => setForm({ ...form, round_type: e.target.value })}
            >
              {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <input
              placeholder="Round name (optional)"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <input
              type="date"
              value={form.round_date}
              onChange={(e) => setForm({ ...form, round_date: e.target.value })}
            />
            <button className="btn-primary" type="submit" disabled={busy}>Add round</button>
          </form>
        )}
      </div>

      {current && (
        <div className="card">
          <div className="pl-sheet-head">
            <h3>
              Round {rounds.indexOf(current) + 1}: {current.name}
              <span className="pl-sub"> · {current.round_type_display}</span>
            </h3>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              {/* the company's shortlist from Excel (meeting point 2) */}
              <ImportExport
                importer="round_results"
                label="round results"
                matchLabel="roll number"
                modes={["upsert"]}
                align="right"
                options={{ round: current.id }}
                note="Only students in this round. Result: Cleared, Not cleared or Absent. The template lists everyone in the round."
                onDone={() => refresh(current.id)}
              />
              {info.can_manage && (
                <button className="btn-delete" type="button" onClick={() => removeRound(current)} disabled={busy}>
                  Delete round
                </button>
              )}
            </div>
          </div>
          <p className="pl-hint">
            {c.in_round || 0} in this round · Cleared {c.cleared || 0} · Not cleared {c.not_cleared || 0} ·
            Absent {c.absent || 0} · Not marked {c.pending || 0}
            {rounds.indexOf(current) > 0 ? " — only students who cleared the previous round appear." : ""}
          </p>

          <table>
            <thead>
              <tr>
                <th>Roll no</th>
                <th>Student</th>
                <th>Department</th>
                <th>Result</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {!sheet ? (
                <tr><td colSpan="5">Loading…</td></tr>
              ) : sheet.results.length === 0 ? (
                <tr>
                  <td colSpan="5">
                    {rounds.indexOf(current) > 0
                      ? "Nobody has cleared the previous round yet."
                      : "Nobody has applied for this role yet."}
                  </td>
                </tr>
              ) : (
                sheet.results.map((r) => (
                  <tr key={r.application}>
                    <td>{r.roll_number || "—"}</td>
                    <td>{r.student_name}</td>
                    <td>{r.department_name || "—"}</td>
                    <td>
                      {r.status
                        ? <span className={`pl-pill is-${r.status}`}>{STATUS_LABEL[r.status]}</span>
                        : <span style={{ color: "#5D5A6B" }}>Not marked</span>}
                    </td>
                    <td>
                      <div className="action-buttons">
                        {["cleared", "not_cleared", "absent"].map((st) => (
                          <button
                            key={st}
                            type="button"
                            className={r.status === st ? (st === "cleared" ? "btn-primary" : "btn-delete") : "btn-edit"}
                            onClick={() => mark([{ application: r.application, status: r.status === st ? "" : st }])}
                            disabled={busy}
                          >
                            {STATUS_LABEL[st]}
                          </button>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>

          {sheet?.results?.some((r) => !r.status) && (
            <div style={{ marginTop: 12 }}>
              <button type="button" className="btn-edit" onClick={markRest} disabled={busy}>
                Mark everyone not marked as "Not cleared"
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
