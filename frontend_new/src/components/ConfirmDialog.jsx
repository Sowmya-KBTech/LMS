// frontend/src/components/ConfirmDialog.jsx
import { useEffect } from "react";
import "../App.css";
/**
 * A blocking confirm dialog.
 *
 * Inline confirm strips push the page content down, so the thing you were
 * reading moves at the moment you have to decide. A warning that says an
 * action cannot be undone should interrupt, not slide in above the table.
 */
export default function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}) {
  // Escape closes it. Without this the only way out is the mouse.
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === "Escape" && !busy) onCancel?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, busy, onCancel]);

  if (!open) return null;

  return (
    <div
      className="cd-backdrop"
      onClick={() => !busy && onCancel?.()}
      role="presentation"
    >
      <div
        className="cd-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cd-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="cd-title" id="cd-title">{title}</h3>
        {body && <div className="cd-body">{body}</div>}
        <div className="cd-actions">
          <button className="ma-btn" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button
            className={`ma-btn ${danger ? "danger" : "primary"}`}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}