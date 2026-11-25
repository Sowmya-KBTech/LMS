// ============================================================
// ImportExport — one small "Import / Export" menu, used on every page
// ============================================================
// Talks to the shared backend engine (/api/dataio/<importer>/...).
//
// One thing on the page:   <ImportExport importer="students" label="students" ... />
// Several in one menu:     <ImportExport sets={[{ importer: "students", ... }, { importer: "staff", ... }]} />
//
// Each set:
//   importer      backend importer key ("students", "ia_marks"...)
//   label         plural name used in the menu ("students")
//   title         section heading when there are several sets ("Students")
//   matchLabel    how existing rows are matched ("roll number")
//   exportParams  filters for Export (e.g. the page's department filter)
//   options       the page's selection, sent with template, export AND import
//                 (e.g. { teaching_assignment: 12, number: 1 })
//   modes         ["add", "upsert"] (default) or ["upsert"] for marks files
//   note          one line shown in the import window
//   canImport     false = no import (e.g. a locked IA)
//
// align="right" opens the menu leftwards (for buttons at the right edge).
// Menu: Download template · Import file… · Export to Excel
// Import: choose file → check (nothing saved) → import (all rows or none).
// New accounts' temporary passwords are offered ONCE for download.
// ============================================================

import { useEffect, useRef, useState } from "react";
import API from "../api";
import Icon from "./Icon";

// ---------------- download helper ----------------
function saveBlob(data, filename, type) {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function filenameFrom(res, fallback) {
  const cd = res.headers?.["content-disposition"] || "";
  const m = cd.match(/filename="?([^";]+)"?/i);
  return m ? m[1] : fallback;
}

// Turn a failed request into a message that says WHY it failed.
// (Downloads use responseType "blob", so a JSON error arrives as a Blob.)
async function errorText(err, fallback) {
  const res = err?.response;
  if (!res) {
    return "Can't reach the server. Make sure the backend is running, then try again.";
  }
  let data = res.data;
  if (data instanceof Blob) {
    try {
      data = JSON.parse(await data.text());
    } catch {
      data = null;
    }
  }
  if (data?.detail) return data.detail;
  if (res.status === 404) {
    return "Import/export isn't available on the server yet. Make sure the updated backend is in place and restart it.";
  }
  if (res.status === 401) return "Your session has expired. Sign in again.";
  if (res.status === 403) return "You don't have permission for this.";
  if (res.status >= 500) {
    return `The server hit an error (${res.status}). The backend terminal shows the details.`;
  }
  return fallback;
}

const csvCell = (v) => {
  const s = String(v ?? "");
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export default function ImportExport({ sets, disabled = false, align = "left", onDone, ...single }) {
  const list = (sets && sets.length ? sets : [single]).map((s) => ({
    label: "records", modes: ["add", "upsert"], canImport: true, exportParams: {}, options: {}, ...s,
  }));

  const [menu, setMenu] = useState(false);
  const [busyKey, setBusyKey] = useState("");     // "template:students" while downloading
  const [active, setActive] = useState(null);     // the set being imported
  const wrapRef = useRef(null);

  // close the menu on outside click / Esc
  useEffect(() => {
    if (!menu) return undefined;
    const onDoc = (e) => wrapRef.current && !wrapRef.current.contains(e.target) && setMenu(false);
    const onKey = (e) => e.key === "Escape" && setMenu(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [menu]);

  const clean = (obj) => {
    const o = {};
    Object.entries(obj || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "" && v !== "all") o[k] = v;
    });
    return o;
  };

  const download = async (set, kind) => {
    setMenu(false);
    setBusyKey(`${kind}:${set.importer}`);
    try {
      const params = kind === "export" ? { ...clean(set.options), ...clean(set.exportParams) } : clean(set.options);
      const res = await API.get(`dataio/${set.importer}/${kind}/`, { params, responseType: "blob" });
      const fallback = kind === "export" ? `${set.importer}.xlsx` : `${set.importer}-template.xlsx`;
      saveBlob(res.data, filenameFrom(res, fallback), res.headers["content-type"]);
    } catch (err) {
      alert(await errorText(err, kind === "export" ? "Couldn't export. Please try again." : "Couldn't download the template."));
    } finally {
      setBusyKey("");
    }
  };

  const busy = Boolean(busyKey);

  return (
    <div className="kb-io" ref={wrapRef}>
      <button
        type="button"
        className="kb-btn kb-io-trigger"
        aria-haspopup="menu"
        aria-expanded={menu}
        disabled={disabled || busy}
        onClick={() => setMenu((m) => !m)}
      >
        <Icon name="table" />
        {busy ? "Preparing file…" : "Import / Export"}
        <Icon name="chevronDown" className="kb-io-chev" />
      </button>

      {menu && (
        <div className={`kb-pop kb-io-menu${align === "right" ? " kb-io-menu--right" : ""}`} role="menu">
          {list.map((set, i) => (
            <div key={set.importer} className="kb-io-sec">
              {list.length > 1 && <div className="kb-io-sec-title">{set.title || set.label}</div>}
              <button type="button" role="menuitem" onClick={() => download(set, "template")}>
                <Icon name="clipboard" /> Download template
              </button>
              {set.canImport && (
                <button type="button" role="menuitem" onClick={() => { setMenu(false); setActive(set); }}>
                  <Icon name="arrowRight" className="kb-io-up" /> Import file…
                </button>
              )}
              <button type="button" role="menuitem" onClick={() => download(set, "export")}>
                <Icon name="arrowRight" className="kb-io-down" /> Export to Excel
              </button>
              {i < list.length - 1 && <hr />}
            </div>
          ))}
        </div>
      )}

      {active && (
        <ImportDialog
          set={active}
          clean={clean}
          onTemplate={() => download(active, "template")}
          onClose={(imported) => {
            setActive(null);
            if (imported) onDone?.();
          }}
        />
      )}
    </div>
  );
}

// ================= THE IMPORT WINDOW =================
function ImportDialog({ set, clean, onTemplate, onClose }) {
  const canUpdate = set.modes.includes("upsert");
  const onlyUpsert = set.modes.length === 1 && set.modes[0] === "upsert";

  const [step, setStep] = useState("choose");     // choose | check | done
  const [file, setFile] = useState(null);
  const [update, setUpdate] = useState(onlyUpsert);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [problem, setProblem] = useState("");
  const [onlyErrors, setOnlyErrors] = useState(true);
  const [loginsSaved, setLoginsSaved] = useState(false);

  const close = () => {
    if (report?.saved && report.extra?.length && !loginsSaved &&
        !window.confirm("You haven't downloaded the login details. The temporary passwords can't be shown again. Close anyway?")) {
      return;
    }
    onClose(Boolean(report?.saved));
  };

  // STEP 7.2: the check / import runs as a background job on the server.
  // Start it, then ask for its status every 2 seconds until it is finished.
  const waitForJob = async (jobId) => {
    const started = Date.now();
    while (Date.now() - started < 6 * 60 * 1000) {        // give up after 6 minutes
      const { data } = await API.get(`jobs/${jobId}/`);
      if (data.status === "done") return data.result;
      if (data.status === "failed") {
        throw Object.assign(new Error(data.error), { jobMessage: data.error || "The import failed. Nothing was saved." });
      }
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    throw Object.assign(new Error("timeout"), {
      jobMessage: "This is taking longer than expected. Check the import history in a minute.",
    });
  };

  const send = async (commit) => {
    if (!file) return;
    setBusy(true);
    setProblem("");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mode", update ? "upsert" : "add");
    fd.append("commit", commit ? "true" : "false");
    Object.entries(clean(set.options)).forEach(([k, v]) => fd.append(k, v));
    try {
      const res = await API.post(`dataio/${set.importer}/start/`, fd);
      const data = await waitForJob(res.data.job_id);
      setReport(data);
      setOnlyErrors(data.counts?.error > 0);
      setStep(commit && data.saved ? "done" : "check");
    } catch (err) {
      const data = err?.response?.data;
      if (err?.jobMessage) {
        setProblem(err.jobMessage);
      } else if (data && (data.file_errors || data.rows)) {
        setReport(data);
        setOnlyErrors(data.counts?.error > 0);
        setStep("check");
      } else {
        setProblem(await errorText(err, "Couldn't check the file. Please try again."));
      }
    } finally {
      setBusy(false);
    }
  };

  const downloadLogins = () => {
    const header = ["Name", "Username", "Roll no / Employee ID", "Email", "Temporary password"];
    const lines = [header, ...(report?.extra || []).map((r) => [r.name, r.username, r.id_number, r.email, r.password])]
      .map((r) => r.map(csvCell).join(","))
      .join("\r\n");
    saveBlob("\ufeff" + lines, `${set.importer}-login-details.csv`, "text/csv");
    setLoginsSaved(true);
  };

  const counts = { total: 0, new: 0, update: 0, skip: 0, error: 0, ...(report?.counts || {}) };
  const rows = (report?.rows || []).filter((r) => !onlyErrors || r.status === "error");
  const hasProblems = counts.error > 0 || report?.file_errors?.length > 0;
  const toSave = counts.new + counts.update;

  return (
    <div className="cd-backdrop" role="dialog" aria-modal="true" aria-label={`Import ${set.label}`}>
      <div className="cd-dialog kb-io-dialog">
        <div className="kb-io-head">
          <h2>Import {set.label}</h2>
          <button type="button" className="kb-icon-btn" aria-label="Close" onClick={close}>
            <Icon name="close" />
          </button>
        </div>

        {/* ---------- choose ---------- */}
        {step === "choose" && (
          <>
            <p className="kb-io-lead">
              Fill the template in Excel, then upload it here. Nothing is saved until you confirm.{" "}
              <button type="button" className="kb-linkbtn" onClick={onTemplate}>Download template</button>
            </p>

            {set.note && <p className="kb-io-lead kb-muted">{set.note}</p>}

            <label className={`kb-io-file${file ? " has-file" : ""}`}>
              <input
                type="file"
                accept=".xlsx,.csv"
                onChange={(e) => { setFile(e.target.files?.[0] || null); setProblem(""); }}
              />
              <span className="kb-btn kb-btn--sm">Choose file</span>
              <span className="kb-io-fname">{file ? file.name : "Excel (.xlsx) or CSV, up to 5,000 rows"}</span>
            </label>

            {canUpdate && !onlyUpsert && (
              <label className="kb-at-check kb-io-check">
                <input type="checkbox" checked={update} onChange={(e) => setUpdate(e.target.checked)} />
                <span>
                  Also update existing {set.label}
                  {set.matchLabel ? ` (matched by ${set.matchLabel})` : ""}. Empty cells never erase data.
                </span>
              </label>
            )}

            {problem && <div className="kb-at-error" role="alert">{problem}</div>}

            <div className="cd-actions">
              <button type="button" className="kb-btn" onClick={close}>Cancel</button>
              <button type="button" className="kb-btn kb-btn--primary" disabled={!file || busy} onClick={() => send(false)}>
                {busy ? "Checking…" : "Check file"}
              </button>
            </div>
          </>
        )}

        {/* ---------- check ---------- */}
        {step === "check" && report && (
          <>
            <div className="kb-io-summary">
              <span className="kb-muted">{file?.name}</span>
              <span className="kb-pill info">{counts.new} new</span>
              <span className="kb-pill info">{counts.update} to update</span>
              {counts.skip > 0 && <span className="kb-pill">{counts.skip} unchanged</span>}
              <span className={`kb-pill ${counts.error ? "bad" : "ok"}`}>{counts.error} with problems</span>
            </div>

            {report.file_errors?.length > 0 && (
              <div className="kb-at-error" role="alert">
                {report.file_errors.map((m) => <div key={m}>{m}</div>)}
              </div>
            )}
            {report.warnings?.map((w) => <div key={w} className="kb-io-warn">{w}</div>)}
            {counts.error > 0 && !report.file_errors?.length && (
              <p className="kb-io-lead">Nothing has been saved. Fix the rows below in your file (row numbers match Excel), then upload it again.</p>
            )}

            {report.rows?.length > 0 && (
              <>
                {counts.error > 0 && (
                  <label className="kb-at-check kb-io-check">
                    <input type="checkbox" checked={onlyErrors} onChange={(e) => setOnlyErrors(e.target.checked)} />
                    <span>Show only rows with problems</span>
                  </label>
                )}
                <div className="table-container kb-io-table">
                  <table>
                    <thead>
                      <tr><th>Row</th><th>{set.matchLabel || "ID"}</th><th>Name</th><th>Result</th></tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.row} className={r.status === "error" ? "is-bad" : ""}>
                          <td className="kb-num">{r.row}</td>
                          <td>{r.key || (r.status === "new" ? <span className="kb-muted">new</span> : "—")}</td>
                          <td>{r.title || "—"}</td>
                          <td>
                            {r.status === "error" ? (
                              <ul className="kb-io-msgs">{r.messages.map((m) => <li key={m}>{m}</li>)}</ul>
                            ) : (
                              <span className="kb-muted">
                                {r.status === "new" ? "Will be added" : r.status === "update" ? "Will be updated" : "No change"}
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            <div className="cd-actions">
              <button type="button" className="kb-btn" onClick={() => { setStep("choose"); setReport(null); }}>
                Choose another file
              </button>
              <button type="button" className="kb-btn kb-btn--primary" disabled={hasProblems || !toSave || busy} onClick={() => send(true)}>
                {busy ? "Importing…" : hasProblems ? "Fix the problems to import" : `Import ${toSave} row${toSave === 1 ? "" : "s"}`}
              </button>
            </div>
          </>
        )}

        {/* ---------- done ---------- */}
        {step === "done" && report && (
          <>
            <div className="kb-io-success">
              <Icon name="check" />
              <span><b>Import complete.</b> {counts.new} added · {counts.update} updated</span>
            </div>

            {report.extra?.length > 0 && (
              <div className="kb-io-logins">
                <span>
                  <b>{report.extra.length} new account{report.extra.length === 1 ? "" : "s"}</b> created with temporary passwords
                  (changed at first login). Download them now — they can't be shown again.
                </span>
                <button type="button" className={`kb-btn kb-btn--sm${loginsSaved ? "" : " kb-btn--primary"}`} onClick={downloadLogins}>
                  {loginsSaved ? "Downloaded ✓" : "Download login details"}
                </button>
              </div>
            )}

            <div className="cd-actions">
              <button type="button" className="kb-btn kb-btn--primary" onClick={close}>Done</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
