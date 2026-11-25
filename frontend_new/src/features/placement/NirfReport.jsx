// NIRF / NAAC placement report for one graduating batch, plus the
// higher-studies list it needs. Download gives a CSV for the IQAC file.
import { useEffect, useState } from "react";
import API from "../../api";

const COLS = [
  ["department", "Department"],
  ["students", "Students"],
  ["placed", "Placed"],
  ["placement_percent", "Placed %"],
  ["median_lpa", "Median (LPA)"],
  ["highest_lpa", "Highest (LPA)"],
  ["average_lpa", "Average (LPA)"],
  ["higher_studies", "Higher studies"],
];

const show = (v) => (v === null || v === undefined ? "—" : v);

export default function NirfReport() {
  const [data, setData] = useState(null);
  const [year, setYear] = useState("");
  const [hs, setHs] = useState([]);
  const [form, setForm] = useState({ roll_number: "", institution: "", programme: "", admission_year: "" });
  const [msg, setMsg] = useState({ ok: "", err: "" });
  const [busy, setBusy] = useState(false);

  const load = (y) => {
    const q = y ? `?passing_year=${y}` : "";
    API.get(`placement/report/nirf/${q}`)
      .then((r) => {
        setData(r.data);
        const py = r.data.passing_year || "";
        setYear(py);
        return API.get(`placement/higher-studies/${py ? `?passing_year=${py}` : ""}`);
      })
      .then((r) => r && setHs(r.data || []))
      .catch(() => setMsg({ ok: "", err: "Could not load the NIRF report." }));
  };

  useEffect(() => { load(""); }, []);

  const download = () => {
    const rows = [...(data?.rows || []), ...(data?.totals ? [data.totals] : [])];
    const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const csv = [COLS.map((c) => esc(c[1])).join(","),
      ...rows.map((r) => COLS.map((c) => esc(r[c[0]])).join(","))].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `placement-nirf-${data.passing_year}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const addHs = async (e) => {
    e.preventDefault();
    setMsg({ ok: "", err: "" });
    try {
      setBusy(true);
      await API.post("placement/higher-studies/", form);
      setForm({ roll_number: "", institution: "", programme: "", admission_year: "" });
      setMsg({ ok: "Higher studies record saved.", err: "" });
      load(year);
    } catch (err) {
      setMsg({ ok: "", err: err.response?.data?.detail || "Could not save." });
    } finally {
      setBusy(false);
    }
  };

  const removeHs = async (h) => {
    if (!window.confirm(`Remove ${h.student_name}'s higher studies record?`)) return;
    await API.delete(`placement/higher-studies/${h.id}/`).catch(() => {});
    load(year);
  };

  if (!data) return msg.err ? <div className="card">{msg.err}</div> : null;

  return (
    <>
      <div className="card">
        <div className="pl-sheet-head">
          <h3>NIRF / NAAC placement report</h3>
          <div className="action-buttons">
            <select value={year} onChange={(e) => load(e.target.value)} disabled={!data.years.length}>
              {data.years.length === 0 && <option value="">No batches</option>}
              {data.years.map((y) => <option key={y} value={y}>{y} batch</option>)}
            </select>
            <button type="button" className="btn-edit" onClick={download} disabled={!data.rows.length}>
              Download CSV
            </button>
          </div>
        </div>
        <p className="pl-hint">
          Graduating batch {show(data.passing_year)}. "Placed" counts students with an accepted
          offer; salaries use each student's highest accepted package.
        </p>
        <div className="pl-table-scroll">
          <table>
            <thead><tr>{COLS.map((c) => <th key={c[0]}>{c[1]}</th>)}</tr></thead>
            <tbody>
              {data.rows.length === 0 ? (
                <tr><td colSpan={COLS.length}>No students found for this batch.</td></tr>
              ) : (
                <>
                  {data.rows.map((r) => (
                    <tr key={r.department}>{COLS.map((c) => <td key={c[0]}>{show(r[c[0]])}</td>)}</tr>
                  ))}
                  <tr className="pl-total">{COLS.map((c) => <td key={c[0]}>{show(data.totals[c[0]])}</td>)}</tr>
                </>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3>Higher studies ({hs.length})</h3>
        <p className="pl-hint">Students who joined a higher-studies programme. NIRF and NAAC ask for this count.</p>
        <form className="form-grid form-grid--row" onSubmit={addHs}>
          <input placeholder="Roll number" value={form.roll_number}
            onChange={(e) => setForm({ ...form, roll_number: e.target.value })} />
          <input placeholder="Institution" value={form.institution}
            onChange={(e) => setForm({ ...form, institution: e.target.value })} />
          <input placeholder="Programme (M.E., MBA…)" value={form.programme}
            onChange={(e) => setForm({ ...form, programme: e.target.value })} />
          <input type="number" placeholder="Year joined" value={form.admission_year}
            onChange={(e) => setForm({ ...form, admission_year: e.target.value })} />
          <button className="btn-primary" type="submit" disabled={busy}>Add</button>
        </form>
        {msg.ok && <p className="pl-ok">{msg.ok}</p>}
        {msg.err && <p className="pl-err">{msg.err}</p>}
        {hs.length > 0 && (
          <table style={{ marginTop: 12 }}>
            <thead>
              <tr><th>Roll no</th><th>Student</th><th>Department</th><th>Institution</th><th>Programme</th><th></th></tr>
            </thead>
            <tbody>
              {hs.map((h) => (
                <tr key={h.id}>
                  <td>{h.roll_number || "—"}</td>
                  <td>{h.student_name}</td>
                  <td>{h.department_name || "—"}</td>
                  <td>{h.institution}</td>
                  <td>{h.programme || "—"}{h.admission_year ? ` (${h.admission_year})` : ""}</td>
                  <td><button type="button" className="btn-delete" onClick={() => removeHs(h)}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
