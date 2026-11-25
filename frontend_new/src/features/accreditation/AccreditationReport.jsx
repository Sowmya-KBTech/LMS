// WAVE 2 - one accreditation report (/accreditation/:key?year=&department=).
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { acApi, cellText, errorText, Pickers, Shell } from "./accreditationApi";
import "../../App.css";
import "../../styles/Accreditation.css";

export default function AccreditationReport() {
  const { key } = useParams();
  const [params, setParams] = useSearchParams();
  const year = params.get("year") || "";
  const department = params.get("department") || "";
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setError("");
    acApi.one(key, { year, department }).then(setData)
      .catch((err) => { setData(null); setError(errorText(err, "Couldn't load the report.")); });
  }, [key, year, department]);

  const choose = ({ year: y, department: d }) => setParams(Object.fromEntries(
    Object.entries({ year: y, department: d }).filter(([, v]) => v !== "" && v != null)));

  const download = async () => {
    setBusy(true);
    setError("");
    try {
      const dept = (data?.department_name || "All").replace(/[^A-Za-z0-9]+/g, "-");
      await acApi.excel(key, { year, department }, `${key}_${data?.year_label || "report"}_${dept}.xlsx`);
    } catch {
      setError("The Excel file couldn't be made. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const r = data?.report;
  const query = params.toString() ? `?${params.toString()}` : "";
  return (
    <Shell
      title={r ? r.title : "Accreditation report"}
      subtitle={data ? `${data.year_label} · ${data.department_name}` : ""}
      actions={(
        <>
          <Link to={`/accreditation${query}`} className="kb-btn">All reports</Link>
          <button type="button" className="kb-btn" onClick={() => window.print()} disabled={!r?.available}>Print / PDF</button>
          <button type="button" className="kb-btn kb-btn--primary" onClick={download} disabled={busy || !r?.available}>
            {busy ? "Preparing…" : "Download Excel"}
          </button>
        </>
      )}
    >
      <section className="kb-card no-print">
        <Pickers meta={data} year={year} department={department} onChange={choose} />
      </section>

      {error && <section className="kb-card"><p className="ac-bad">{error}</p></section>}
      {!data && !error && <section className="kb-card"><p className="ac-muted">Loading…</p></section>}

      {r && (
        <section className="kb-card">
          <div className="ac-report-head">
            <span className="ac-supports-tag">{r.supports}</span>
            <span className="ac-print-only">{data.year_label} · {data.department_name}</span>
          </div>
          <p className="ac-muted">{r.note}</p>

          {!r.available ? null : r.rows.length === 0 ? (
            <p className="ac-empty">Nothing to count for this year and department yet.</p>
          ) : (
            <div className="ac-table-wrap">
              <table className="ac-table">
                <thead>
                  <tr>{r.columns.map((c) => <th key={c.key} className={c.type !== "text" ? "num" : ""}>{c.label}</th>)}</tr>
                </thead>
                <tbody>
                  {r.rows.map((row, i) => (
                    <tr key={i}>
                      {r.columns.map((c) => (
                        <td key={c.key} className={c.type !== "text" ? "num" : ""}>{cellText(row[c.key], c.type)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
                {r.total && (
                  <tfoot>
                    <tr>
                      {r.columns.map((c) => (
                        <td key={c.key} className={c.type !== "text" ? "num" : ""}>
                          {r.total[c.key] === undefined ? "" : cellText(r.total[c.key], c.type)}
                        </td>
                      ))}
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          )}
        </section>
      )}
    </Shell>
  );
}
