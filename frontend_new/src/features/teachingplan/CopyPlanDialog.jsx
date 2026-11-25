// COURSE PLAN (Part C) - copy another plan of the same subject into this one.
// Sources: my other plans of the subject, and other teachers' approved plans
// of it (another section). Topics, units, modes, methods, activities and
// outcomes are copied; dates come from THIS semester's timetable, in order.
// What was delivered is never copied.
import { useEffect, useRef, useState } from "react";
import API from "../../api";
import "../../styles/CoursePlan.css";

const dmy = (iso) => { if (!iso) return ""; const [y, m, d] = iso.split("-"); return `${d}-${m}-${y}`; };

export default function CopyPlanDialog({ subjectId, sessionKeys, plannedKeys, onClose, onCopied }) {
  const [sources, setSources] = useState(null);
  const [error, setError] = useState("");
  const [pick, setPick] = useState(null);
  const [replace, setReplace] = useState(plannedKeys.size === 0);
  const [busy, setBusy] = useState(false);
  const boxRef = useRef(null);

  useEffect(() => {
    API.get(`teaching-plans/copy_sources/?subject=${subjectId}`)
      .then((r) => {
        const list = r.data?.sources || [];
        setSources(list);
        if (list.length) setPick(list[0].id);
      })
      .catch((e) => setError(e?.response?.data?.detail || "Could not load plans to copy from."));
  }, [subjectId]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && !busy && onClose();
    document.addEventListener("keydown", onKey);
    boxRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const src = (sources || []).find((s) => s.id === pick);
  // what will happen: topic i goes to timetable session i
  const fillCount = (() => {
    if (!src) return 0;
    const n = Math.min(src.sessions, sessionKeys.length);
    return replace ? n : n - sessionKeys.slice(0, n).filter((k) => plannedKeys.has(k)).length;
  })();
  const preview = (() => {
    if (!src) return "";
    if (fillCount === 0) return "Every session this plan would fill is already planned. Tick “Replace” to overwrite them.";
    const n = Math.min(src.sessions, sessionKeys.length);
    const kept = replace ? 0 : sessionKeys.slice(0, n).filter((k) => plannedKeys.has(k)).length;
    const fill = n - kept;
    const extra = Math.max(0, src.sessions - sessionKeys.length);
    const parts = [`${fill} topic${fill === 1 ? "" : "s"} will fill ${fill} of your ${sessionKeys.length} sessions.`];
    if (kept) parts.push(`${kept} session${kept === 1 ? " you have" : "s you have"} already planned ${kept === 1 ? "stays as it is" : "stay as they are"}.`);
    if (replace && plannedKeys.size) parts.push(`Your ${plannedKeys.size} planned session${plannedKeys.size === 1 ? " is" : "s are"} replaced.`);
    if (extra) parts.push(`${extra} topic${extra === 1 ? " does" : "s do"} not fit your timetable.`);
    return parts.join(" ");
  })();

  const copy = async () => {
    if (!src) return;
    setBusy(true);
    setError("");
    try {
      const r = await API.post("teaching-plans/copy/", { subject: subjectId, source: src.id, replace });
      onCopied(r.data?.message || "Copied.");
    } catch (e) {
      setError(e?.response?.data?.detail || "Not copied. Try again.");
      setBusy(false);
    }
  };

  return (
    <div className="cp-modal-back" onMouseDown={(e) => e.target === e.currentTarget && !busy && onClose()}>
      <div className="cp-modal" role="dialog" aria-modal="true" aria-labelledby="cp-copy-h" tabIndex={-1} ref={boxRef}>
        <div className="cp-modal-head">
          <h2 id="cp-copy-h">Copy a plan</h2>
          <button type="button" className="cp-btn" aria-label="Close" onClick={onClose} disabled={busy}>×</button>
        </div>
        <p className="cp-muted">Reuse topics, units, teaching modes and outcomes. Dates are filled again from this
          semester’s timetable, in order. What was delivered is not copied.</p>

        {sources === null && !error && <p className="cp-muted">Loading…</p>}
        {sources && sources.length === 0 && (
          <div className="tp-note">No plan of this subject to copy yet. You can copy your own other plans of this subject,
            or another section’s plan once its HOD has approved it.</div>
        )}
        {sources && sources.length > 0 && (
          <fieldset className="cp-src">
            <legend>Copy from</legend>
            {sources.map((s) => (
              <label key={s.id} className={pick === s.id ? "on" : ""}>
                <input type="radio" name="cp-src" checked={pick === s.id} onChange={() => setPick(s.id)} />
                <span>
                  <b>{s.mine ? "My plan" : s.teacher} · {s.cls}</b>
                  <small>{s.sem} · {s.status.toLowerCase()} · {s.sessions} session{s.sessions === 1 ? "" : "s"} · updated {dmy(s.updated)}</small>
                </span>
              </label>
            ))}
          </fieldset>
        )}

        {src && (
          <>
            <label className="cp-check">
              <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
              Replace the sessions I have already planned
            </label>
            <div className="cp-alert cp-alert-soft" role="status"><span>{preview}</span></div>
          </>
        )}
        {error && <div className="cp-msg bad" role="alert">{error}</div>}

        <div className="cp-modal-foot">
          <button type="button" className="tp-btn-outline tp-btn-sm" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className="tp-btn-primary tp-btn-sm" onClick={copy} disabled={!src || busy || fillCount === 0}>
            {busy ? "Copying…" : "Copy plan"}</button>
        </div>
      </div>
    </div>
  );
}
