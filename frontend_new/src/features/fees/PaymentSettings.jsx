// frontend/src/features/fees/PaymentSettings.jsx
//
// PHASE 3 - this college's own Razorpay account.
// Shown as the "Online payments" tab on the admin Fees page. The college admin
// (or accounts admin) saves the college's Razorpay keys here, so fees paid at
// this college's address go to this college's own bank account.
//
// The secrets are never shown again after saving - only "Saved". Leave a
// secret blank to keep the saved one.

import { useEffect, useState } from "react";
import API from "../../api";

const BRAND = "#4B32C3";
const INK = "#17151F";
const MUTED = "#5D5A6B";
const LINE = "#E7E7EC";
const HAIR = "#ECECF0";

const card = {
  background: "#fff", border: `1px solid ${LINE}`, borderRadius: 14, padding: "20px 22px",
};
const label = { display: "block", fontSize: 14, fontWeight: 600, color: INK, marginBottom: 6 };
const hint = { fontSize: 13.5, color: MUTED, marginTop: 5, lineHeight: 1.45 };
const input = {
  width: "100%", padding: "10px 12px", borderRadius: 9, border: `1px solid ${LINE}`,
  fontSize: 15, boxSizing: "border-box", fontFamily: "inherit", background: "#fbfcfe",
};
const btn = (kind, disabled) => ({
  padding: "9px 18px", borderRadius: 10, fontSize: 14.5, fontWeight: 600,
  cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.55 : 1,
  ...(kind === "primary" && { border: "none", background: BRAND, color: "#fff" }),
  ...(kind === "plain" && { border: `1px solid ${LINE}`, background: "#fff", color: INK }),
  ...(kind === "danger" && { border: "1px solid #fecaca", background: "#fff", color: "#B42318" }),
});

function StatusBadge({ data }) {
  let text = "Not set up";
  let style = { background: "#fff7ed", color: "#8A4B0A", border: "1px solid #fed7aa" };
  if (data?.configured) {
    text = data.mode === "live" ? "Set up · Live" : "Set up · Test mode";
    style = data.mode === "live"
      ? { background: "#ecfdf5", color: "#15803d", border: "1px solid #bbf7d0" }
      : { background: "#eef2ff", color: BRAND, border: "1px solid #c7d2fe" };
  }
  return (
    <span style={{
      display: "inline-block", fontSize: 13, fontWeight: 700, borderRadius: 999,
      padding: "4px 12px", whiteSpace: "nowrap", ...style,
    }}>
      {text}
    </span>
  );
}

function Message({ msg }) {
  if (!msg) return null;
  const ok = msg.type === "ok";
  return (
    <div role={ok ? "status" : "alert"} style={{
      marginTop: 14, padding: "10px 14px", borderRadius: 10, fontSize: 14.5, lineHeight: 1.45,
      background: ok ? "#ecfdf5" : "#fef2f2",
      border: `1px solid ${ok ? "#bbf7d0" : "#fecaca"}`,
      color: ok ? "#15803d" : "#B42318",
    }}>
      {msg.text}
    </div>
  );
}

export default function PaymentSettings() {
  const [data, setData] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [form, setForm] = useState({ key_id: "", key_secret: "", webhook_secret: "" });
  const [busy, setBusy] = useState("");          // "", "save", "test", "remove"
  const [msg, setMsg] = useState(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [copied, setCopied] = useState(false);

  const show = (d) => {
    setData(d);
    setForm({ key_id: d.key_id || "", key_secret: "", webhook_secret: "" });
  };

  useEffect(() => {
    API.get("/payments/settings/")
      .then((r) => show(r.data))
      .catch((err) => setLoadError(
        err.response?.data?.detail || "Could not load the payment settings."));
  }, []);

  const set = (k) => (e) => { setForm({ ...form, [k]: e.target.value }); setMsg(null); };

  const save = async () => {
    setBusy("save"); setMsg(null);
    try {
      const body = { key_id: form.key_id.trim(), key_secret: form.key_secret.trim() };
      if (form.webhook_secret.trim()) body.webhook_secret = form.webhook_secret.trim();
      const r = await API.put("/payments/settings/", body);
      show(r.data);
      setMsg({ type: "ok", text: "Saved. Students and parents can now pay fees online into this college's Razorpay account." });
    } catch (err) {
      setMsg({ type: "bad", text: err.response?.data?.detail || "Could not save. Try again." });
    } finally {
      setBusy("");
    }
  };

  const test = async () => {
    setBusy("test"); setMsg(null);
    try {
      const r = await API.post("/payments/settings/test/", {
        key_id: form.key_id.trim(), key_secret: form.key_secret.trim(),
      });
      setMsg({ type: "ok", text: r.data.detail });
    } catch (err) {
      setMsg({ type: "bad", text: err.response?.data?.detail || "Could not test the keys." });
    } finally {
      setBusy("");
    }
  };

  const remove = async () => {
    setBusy("remove"); setMsg(null);
    try {
      const r = await API.delete("/payments/settings/");
      show(r.data);
      setConfirmRemove(false);
      setMsg({ type: "ok", text: "Keys removed. Online payment is switched off for this college." });
    } catch (err) {
      setMsg({ type: "bad", text: err.response?.data?.detail || "Could not remove the keys." });
    } finally {
      setBusy("");
    }
  };

  const copyWebhook = async () => {
    try {
      await navigator.clipboard.writeText(data.webhook_url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      /* the link is visible to copy by hand */
    }
  };

  if (loadError) {
    return <div style={{ ...card, color: MUTED, fontSize: 15 }}>{loadError}</div>;
  }
  if (!data) {
    return <div style={{ ...card, color: MUTED, fontSize: 15 }}>Loading…</div>;
  }

  const keyIdOk = /^rzp_(test|live)_[A-Za-z0-9]{6,40}$/.test(form.key_id.trim());
  const newKey = form.key_id.trim() !== (data.key_id || "");
  const needSecret = newKey || !data.has_key_secret;
  const canSave = keyIdOk && (!needSecret || form.key_secret.trim()) && !busy;
  const canTest = keyIdOk && (!needSecret || form.key_secret.trim()) && !busy;

  return (
    <div style={{ display: "grid", gap: 16, maxWidth: 760 }}>
      {/* ---------- status ---------- */}
      <div style={{ ...card, display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, color: INK }}>Razorpay account</div>
          <div style={{ ...hint, marginTop: 3 }}>
            Online fee payments go to the Razorpay account saved here, and from there
            to this college's bank account.
            {data.updated_by && ` Last changed by ${data.updated_by}.`}
          </div>
        </div>
        <StatusBadge data={data} />
      </div>

      {/* ---------- keys ---------- */}
      <div style={card}>
        <div style={{ display: "grid", gap: 18 }}>
          <div>
            <label style={label} htmlFor="ps-key-id">Key ID</label>
            <input id="ps-key-id" style={input} value={form.key_id} onChange={set("key_id")}
              placeholder="rzp_test_XXXXXXXXXXXX" autoComplete="off" spellCheck={false} />
            <div style={hint}>
              Starts with <b>rzp_test_</b> (practice, no real money) or <b>rzp_live_</b> (real payments).
            </div>
          </div>

          <div>
            <label style={label} htmlFor="ps-key-secret">Key Secret</label>
            <input id="ps-key-secret" style={input} type="password" value={form.key_secret}
              onChange={set("key_secret")} autoComplete="new-password"
              placeholder={data.has_key_secret && !newKey ? "Saved · leave blank to keep" : "Paste the Key Secret"} />
            <div style={hint}>Stored encrypted and never shown again.</div>
          </div>

          <div>
            <label style={label} htmlFor="ps-webhook-secret">Webhook Secret</label>
            <input id="ps-webhook-secret" style={input} type="password" value={form.webhook_secret}
              onChange={set("webhook_secret")} autoComplete="new-password"
              placeholder={data.has_webhook_secret ? "Saved · leave blank to keep" : "The secret you set when adding the webhook in Razorpay"} />
            <div style={hint}>
              Confirms a payment even if the student closes the page right after paying.
            </div>
          </div>

          <div>
            <span style={label}>Webhook URL to add in Razorpay</span>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <code style={{
                flex: "1 1 320px", padding: "10px 12px", borderRadius: 9, background: "#F6F6F9",
                border: `1px solid ${HAIR}`, fontSize: 13.5, color: INK, wordBreak: "break-all",
              }}>
                {data.webhook_url}
              </code>
              <button type="button" style={btn("plain", false)} onClick={copyWebhook}>
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <div style={hint}>In Razorpay, choose the event <b>payment.captured</b>.</div>
          </div>
        </div>

        <Message msg={msg} />

        <div style={{ display: "flex", gap: 10, marginTop: 18, flexWrap: "wrap", alignItems: "center" }}>
          <button type="button" style={btn("plain", !canTest)} disabled={!canTest} onClick={test}>
            {busy === "test" ? "Testing…" : "Test connection"}
          </button>
          <button type="button" style={btn("primary", !canSave)} disabled={!canSave} onClick={save}>
            {busy === "save" ? "Saving…" : "Save"}
          </button>
          <span style={{ flex: 1 }} />
          {data.configured && !confirmRemove && (
            <button type="button" style={btn("danger", !!busy)} disabled={!!busy}
              onClick={() => setConfirmRemove(true)}>
              Remove keys
            </button>
          )}
          {confirmRemove && (
            <>
              <span style={{ fontSize: 14, color: "#B42318" }}>Switch off online payment?</span>
              <button type="button" style={btn("danger", !!busy)} disabled={!!busy} onClick={remove}>
                {busy === "remove" ? "Removing…" : "Yes, remove"}
              </button>
              <button type="button" style={btn("plain", false)} onClick={() => setConfirmRemove(false)}>
                Cancel
              </button>
            </>
          )}
        </div>
      </div>

      {/* ---------- how to ---------- */}
      <div style={card}>
        <div style={{ fontSize: 15, fontWeight: 600, color: INK, marginBottom: 8 }}>
          How to get these from Razorpay
        </div>
        <ol style={{ margin: 0, paddingLeft: 20, color: MUTED, fontSize: 14.5, lineHeight: 1.7 }}>
          <li>Sign in to the college's own Razorpay account at dashboard.razorpay.com.</li>
          <li>Choose <b>Test mode</b> to practise, or <b>Live mode</b> after Razorpay approves the college's KYC.</li>
          <li>Open the API keys settings and generate a key. Copy the <b>Key ID</b> and <b>Key Secret</b> here.</li>
          <li>Open the webhook settings, add the webhook URL above with the event <b>payment.captured</b>, set a secret, and paste that secret here.</li>
          <li>Click <b>Test connection</b>, then <b>Save</b>.</li>
        </ol>
      </div>
    </div>
  );
}
