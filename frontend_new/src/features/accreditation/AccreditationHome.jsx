// WAVE 2 - accreditation reports home (/accreditation): pick a year and a
// department, see a headline for each of the 8 reports, open one.
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { acApi, errorText, Pickers, Shell } from "./accreditationApi";
import "../../App.css";
import "../../styles/Accreditation.css";

export default function AccreditationHome() {
  const [params, setParams] = useSearchParams();
  const year = params.get("year") || "";
  const department = params.get("department") || "";
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    acApi.list({ year, department }).then(setData)
      .catch((err) => { setData(null); setError(errorText(err, "Couldn't load the reports.")); });
  }, [year, department]);

  const choose = ({ year: y, department: d }) => setParams(Object.fromEntries(
    Object.entries({ year: y, department: d }).filter(([, v]) => v !== "" && v != null)));
  const query = params.toString() ? `?${params.toString()}` : "";

  return (
    <Shell
      title="Accreditation reports"
      subtitle={data ? `NAAC / NBA numbers for ${data.year_label} · ${data.department_name}`
        : "NAAC / NBA numbers, counted from what is already in KB Tech Campus"}
    >
      <section className="kb-card">
        <Pickers meta={data} year={year} department={department} onChange={choose} />
        {data && !data.college_wide && (
          <p className="ac-muted ac-gap">As HOD you see your own department's reports.</p>
        )}
      </section>

      {error && <section className="kb-card"><p className="ac-bad">{error}</p></section>}
      {!data && !error && <section className="kb-card"><p className="ac-muted">Loading…</p></section>}

      {data && (
        <div className="ac-cards">
          {data.reports.map((r, i) => (
            <Link key={r.key} to={`/accreditation/${r.key}${query}`} className={`ac-card${r.available ? "" : " off"}`}>
              <span className="ac-no">{i + 1}</span>
              <b className="ac-card-title">{r.title}</b>
              <span className="ac-headline">{r.headline}</span>
              <span className="ac-supports">{r.supports}</span>
              <span className="ac-open">Open report →</span>
            </Link>
          ))}
        </div>
      )}

      <p className="ac-muted ac-gap">
        These reports only read data already in the system: student records, results, surveys, mentoring,
        My Contributions, placement and attendance. Download each one as Excel to copy into the NAAC / NBA forms.
      </p>
    </Shell>
  );
}
