// PLATFORM CONSOLE - KB Technosoft's own screens.
//
// Shown instead of the college app when the site is opened at the platform
// address (localhost:5173, later admin.kbtechcampus.in). It signs in with a
// KB Technosoft account - never a college account - and manages colleges:
// list, add, details, switch off / on, reset a college admin's password.
// It sees totals only, never a student, a mark or a fee.

import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { API_BASE_URL, COLLEGE_DOMAIN_SUFFIX } from "../../apiBase";
import "./platform.css";
// the platform sign-in uses the same look as the college login page
import "../../App.css";
import Icon from "../../components/Icon";
import kbLogo from "../../assets/kb-logo.png";

const TOKEN_KEY = "platform_token";
const USER_KEY = "platform_user";

const platformAPI = axios.create({ baseURL: `${API_BASE_URL}platform/` });
platformAPI.interceptors.request.use((req) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) req.headers.Authorization = `Bearer ${token}`;
  return req;
});

const errorText = (err, fallback) =>
  err?.response?.data?.detail || (err?.response ? fallback : "Can't reach the server. Is the backend running?");

// a college's own address, opened from the platform (keeps the dev port, e.g. :5173)
const collegeUrl = (domain) => {
  const port = window.location.port ? `:${window.location.port}` : "";
  return `${window.location.protocol}//${domain}${port}/`;
};

export default function PlatformApp() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState(() => localStorage.getItem(USER_KEY) || "");
  const [view, setView] = useState({ name: "list" });

  const signOut = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken(null);
    setView({ name: "list" });
  }, []);

  // an expired or refused platform token sends you back to sign in
  useEffect(() => {
    const id = platformAPI.interceptors.response.use(
      (res) => res,
      (err) => {
        if (err?.response?.status === 401) signOut();
        return Promise.reject(err);
      },
    );
    return () => platformAPI.interceptors.response.eject(id);
  }, [signOut]);

  if (!token) {
    return (
      <PlatformLogin
        onSignedIn={(access, username) => {
          localStorage.setItem(TOKEN_KEY, access);
          localStorage.setItem(USER_KEY, username);
          setUser(username);
          setToken(access);
        }}
      />
    );
  }

  return (
    <div className="pf">
      <header className="pf-top">
        <div className="pf-brand">
          <div className="pf-logo">KB</div>
          <div>
            <div className="pf-brand-name">KB Tech Campus</div>
            <div className="pf-brand-sub">Platform console</div>
          </div>
        </div>
        <nav className="pf-nav" aria-label="Platform">
          <button
            type="button"
            className={view.name !== "add" ? "pf-nav-on" : ""}
            onClick={() => setView({ name: "list" })}
          >
            Colleges
          </button>
        </nav>
        <div className="pf-user">
          <span className="pf-avatar" aria-hidden="true">{(user || "K").slice(0, 2).toUpperCase()}</span>
          <span>{user}</span>
          <button
            type="button"
            className="pf-btn pf-btn-ghost"
            onClick={() => {
              // PHASE 5 PART 4: end this token on the server too, then sign out here
              platformAPI.post("logout/").catch(() => {}).finally(signOut);
            }}
          >Sign out</button>
        </div>
      </header>

      <main className="pf-main">
        {view.name === "list" && (
          <CollegeList onAdd={() => setView({ name: "add" })} onOpen={(id) => setView({ name: "detail", id })} />
        )}
        {view.name === "add" && (
          <AddCollege onCancel={() => setView({ name: "list" })} onCreated={(id) => setView({ name: "detail", id })} />
        )}
        {view.name === "detail" && <CollegeDetail id={view.id} onBack={() => setView({ name: "list" })} />}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------- sign in
const PLATFORM_FEATURES = [
  { icon: "building", title: "Every college in one place", text: "See each college, its address, its status and its totals." },
  { icon: "plus", title: "Add a college in a minute", text: "Its own private data, its own address and its first admin." },
  { icon: "shield", title: "Totals only, never student data", text: "Switch a college off or on, and help its admins sign in." },
];

function PlatformLogin({ onSignedIn }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!username.trim() || !password) {
      setError("Enter your username and password.");
      return;
    }
    setBusy(true);
    try {
      const { data } = await platformAPI.post("login/", { username, password });
      onSignedIn(data.access, data.username);
    } catch (err) {
      setError(errorText(err, "Could not sign in."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="kb-auth">
      {/* ---------- left: brand panel (same as the college login) ---------- */}
      <aside className="kb-auth-panel">
        <div className="kb-auth-brand">
          <img src={kbLogo} alt="KB Tech logo" />
          <div>
            <b>KB Tech Campus</b>
            <small>Platform console</small>
          </div>
        </div>

        <div className="kb-auth-pitch">
          <h1>Every college.<br />One console.<br /><span>KB Technosoft only.</span></h1>
          <ul>
            {PLATFORM_FEATURES.map((f) => (
              <li key={f.title}>
                <span className="kb-auth-fico"><Icon name={f.icon} /></span>
                <div>
                  <b>{f.title}</b>
                  <p>{f.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <small className="kb-auth-copy">© KB Technosoft Private Limited</small>
      </aside>

      {/* ---------- right: the form ---------- */}
      <main className="kb-auth-main">
        <form className="kb-auth-form" onSubmit={submit} noValidate>
          <div className="kb-auth-mbrand">
            <img src={kbLogo} alt="" />
            <b>KB Tech Campus</b>
          </div>

          <div>
            <h2>Platform sign in</h2>
            <p className="kb-lede">
              For KB Technosoft staff. College users sign in at their college's own address.
            </p>
          </div>

          <label className="kb-field">
            <span>Username</span>
            <div className="kb-ifield">
              <Icon name="user" />
              <input
                className="kb-input"
                name="username"
                autoComplete="username"
                placeholder="kbadmin"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
          </label>

          <label className="kb-field">
            <span>Password</span>
            <div className="kb-ifield">
              <Icon name="lock" />
              <input
                className="kb-input"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                className="kb-eye"
                aria-label={showPassword ? "Hide password" : "Show password"}
                onClick={() => setShowPassword((s) => !s)}
              >
                <Icon name={showPassword ? "eyeOff" : "eye"} />
              </button>
            </div>
          </label>

          {error && <div className="kb-err" role="alert">{error}</div>}

          <button className="kb-btn kb-btn--primary kb-cta" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
            {!busy && <Icon name="arrowRight" />}
          </button>

          <div className="kb-auth-info">
            <Icon name="shield" />
            <span>Only KB Technosoft platform accounts can sign in here.</span>
          </div>
        </form>
      </main>
    </div>
  );
}

// ---------------------------------------------------------------- colleges list
function CollegeList({ onAdd, onOpen }) {
  const [colleges, setColleges] = useState(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    platformAPI
      .get("colleges/")
      .then((r) => setColleges(r.data))
      .catch((err) => setError(errorText(err, "Could not load colleges.")));
  }, []);

  const shown = (colleges || []).filter((c) => {
    const q = search.trim().toLowerCase();
    return !q || c.name.toLowerCase().includes(q) || c.code.includes(q);
  });
  const active = (colleges || []).filter((c) => c.is_active).length;

  return (
    <>
      <div className="pf-head">
        <div>
          <h1 className="pf-h1">Colleges</h1>
          <p className="pf-muted">Each college is a tenant with its own address and its own private data.</p>
        </div>
        <button type="button" className="pf-btn pf-btn-primary" onClick={onAdd}>+ Add college</button>
      </div>

      {error && <div className="pf-alert pf-alert-bad" role="alert">{error}</div>}

      <div className="pf-stats">
        <Stat label="Colleges" value={colleges ? colleges.length : "—"} />
        <Stat label="Active" value={colleges ? active : "—"} tone="ok" />
        <Stat label="Switched off" value={colleges ? colleges.length - active : "—"} tone="bad" />
      </div>

      <div className="pf-card pf-flush">
        <div className="pf-card-bar">
          <label className="pf-visually-hidden" htmlFor="pf-search">Search colleges</label>
          <input
            id="pf-search"
            className="pf-search"
            type="search"
            placeholder="Search by name or code"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <span className="pf-muted">{colleges ? `Showing ${shown.length} of ${colleges.length}` : "Loading…"}</span>
        </div>
        <div className="pf-scroll">
          <table className="pf-table">
            <thead>
              <tr>
                <th>Tenant ID</th>
                <th>College</th>
                <th>Address</th>
                <th>Schema</th>
                <th className="pf-num">Students</th>
                <th className="pf-num">Teachers</th>
                <th>Status</th>
                <th>Online payments</th>
                <th><span className="pf-visually-hidden">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {colleges && shown.length === 0 && (
                <tr><td colSpan={9} className="pf-empty">No colleges yet. Add the first one.</td></tr>
              )}
              {shown.map((c) => (
                <tr key={c.id}>
                  <td className="pf-strong">{c.id}</td>
                  <td>
                    <div className="pf-college">
                      <CollegeMark college={c} />
                      <span className="pf-strong">{c.name}</span>
                    </div>
                  </td>
                  <td>{c.domain ? <a href={collegeUrl(c.domain)} target="_blank" rel="noreferrer">{c.domain}</a> : "—"}</td>
                  <td className="pf-mono">{c.code}</td>
                  <td className="pf-num">{c.counts?.students ?? "—"}</td>
                  <td className="pf-num">{c.counts?.teachers ?? "—"}</td>
                  <td><StatusBadge active={c.is_active} /></td>
                  <td><PaymentsBadge status={c.online_payments} /></td>
                  <td className="pf-right">
                    <button type="button" className="pf-btn pf-btn-ghost" onClick={() => onOpen(c.id)}>Manage</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="pf-alert pf-alert-info">
        The platform console manages colleges only. Students, staff, marks, attendance and fees stay inside each
        college's own schema and never appear here.
      </div>
    </>
  );
}

// ---------------------------------------------------------------- add a college
function AddCollege({ onCancel, onCreated }) {
  const [form, setForm] = useState({ name: "", code: "", admin_username: "", admin_password: "", admin_email: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (key) => (e) => {
    let value = e.target.value;
    if (key === "code") value = value.toLowerCase().replace(/[^a-z0-9]/g, "");
    setForm((f) => ({ ...f, [key]: value }));
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const { data } = await platformAPI.post("colleges/", form);
      onCreated(data.id);
    } catch (err) {
      setError(errorText(err, "Could not create the college."));
      setBusy(false);
    }
  };

  const code = form.code || "code";

  return (
    <>
      <button type="button" className="pf-link" onClick={onCancel}>← Back to colleges</button>
      <div className="pf-head">
        <div>
          <h1 className="pf-h1">Add a college</h1>
          <p className="pf-muted">Creates a new tenant: its Tenant ID, a private schema and its own web address.</p>
        </div>
      </div>

      <div className="pf-split">
        <form className="pf-stack" onSubmit={submit}>
          <section className="pf-card">
            <h2 className="pf-h2">College details</h2>
            <label className="pf-field">
              <span>College name</span>
              <input value={form.name} onChange={set("name")} placeholder="e.g. PQR Engineering College" required />
            </label>
            <label className="pf-field">
              <span>Short code</span>
              <div className="pf-affix">
                <input value={form.code} onChange={set("code")} placeholder="e.g. pqr" maxLength={30} required />
                <span>.{COLLEGE_DOMAIN_SUFFIX}</span>
              </div>
              <small className="pf-muted">
                Lowercase letters and digits, starting with a letter. Becomes the address and the schema name, and
                cannot be changed later.
              </small>
            </label>
            <div className="pf-preview">
              <div><small>Web address</small><b>{code}.{COLLEGE_DOMAIN_SUFFIX}</b></div>
              <div><small>Private schema</small><b className="pf-mono">{code}</b></div>
            </div>
          </section>

          <section className="pf-card">
            <h2 className="pf-h2">First college admin</h2>
            <p className="pf-muted">This person becomes the college's master admin and creates the HODs.</p>
            <div className="pf-grid2">
              <label className="pf-field">
                <span>Username</span>
                <input value={form.admin_username} onChange={set("admin_username")} placeholder="e.g. pqradmin" required />
              </label>
              <label className="pf-field">
                <span>Email (optional)</span>
                <input type="email" value={form.admin_email} onChange={set("admin_email")} />
              </label>
              <label className="pf-field">
                <span>Password</span>
                <input
                  type="password"
                  value={form.admin_password}
                  onChange={set("admin_password")}
                  autoComplete="new-password"
                  required
                />
              </label>
            </div>
          </section>

          {error && <div className="pf-alert pf-alert-bad" role="alert">{error}</div>}
          {busy && (
            <div className="pf-alert pf-alert-info" role="status">
              Creating the college and building its tables. This can take up to a minute; please keep this page open.
            </div>
          )}

          <div className="pf-actions">
            <button type="button" className="pf-btn pf-btn-ghost" onClick={onCancel} disabled={busy}>Cancel</button>
            <button type="submit" className="pf-btn pf-btn-primary" disabled={busy}>
              {busy ? "Creating…" : "Create college"}
            </button>
          </div>
        </form>

        <aside className="pf-card pf-aside">
          <h2 className="pf-h2">What happens when you create</h2>
          <ol className="pf-steps">
            <li>The college gets its <b>Tenant ID</b> in the shared college list.</li>
            <li>A <b>private schema</b> is built with every table, empty.</li>
            <li>Its <b>web address</b> works at once.</li>
            <li>The <b>college admin</b> signs in there and sets up the college.</li>
          </ol>
        </aside>
      </div>
    </>
  );
}

// ---------------------------------------------------------------- one college
function CollegeDetail({ id, onBack }) {
  const [college, setCollege] = useState(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [reset, setReset] = useState({ username: "", new_password: "" });

  useEffect(() => {
    platformAPI
      .get(`colleges/${id}/`)
      .then((r) => setCollege(r.data))
      .catch((err) => setError(errorText(err, "Could not load this college.")));
  }, [id]);

  const switchCollege = async () => {
    const turningOff = college.is_active;
    if (turningOff && !window.confirm(
      `Switch off ${college.name}? Its users will not be able to sign in until you switch it back on. No data is deleted.`,
    )) return;
    setBusy(true);
    setError("");
    setNote("");
    try {
      const { data } = await platformAPI.patch(`colleges/${id}/`, { is_active: !turningOff });
      setCollege(data);
      setNote(data.is_active ? "College switched on." : "College switched off. Its data is kept.");
    } catch (err) {
      setError(errorText(err, "Could not change the status."));
    } finally {
      setBusy(false);
    }
  };

  // COLLEGE LOGO: shown on the college's sign-in page
  const uploadLogo = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";                         // allow choosing the same file again
    if (!file) return;
    setBusy(true);
    setError("");
    setNote("");
    try {
      const form = new FormData();
      form.append("logo", file);
      const { data } = await platformAPI.post(`colleges/${id}/logo/`, form);
      setCollege(data);
      setNote("Logo saved. It now shows on the college's sign-in page.");
    } catch (err) {
      setError(errorText(err, "Could not save the logo."));
    } finally {
      setBusy(false);
    }
  };

  const removeLogo = async () => {
    if (!window.confirm("Remove this college's logo?")) return;
    setBusy(true);
    setError("");
    setNote("");
    try {
      const { data } = await platformAPI.delete(`colleges/${id}/logo/`);
      setCollege(data);
      setNote("Logo removed.");
    } catch (err) {
      setError(errorText(err, "Could not remove the logo."));
    } finally {
      setBusy(false);
    }
  };

  const resetPassword = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    setNote("");
    try {
      const { data } = await platformAPI.post(`colleges/${id}/reset-admin-password/`, reset);
      setNote(data.detail);
      setReset({ username: "", new_password: "" });
    } catch (err) {
      setError(errorText(err, "Could not reset the password."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button type="button" className="pf-link" onClick={onBack}>← Back to colleges</button>
      {error && <div className="pf-alert pf-alert-bad" role="alert">{error}</div>}
      {note && <div className="pf-alert pf-alert-ok" role="status">{note}</div>}
      {!college && !error && <p className="pf-muted">Loading…</p>}

      {college && (
        <>
          <div className="pf-head">
            <div className="pf-college">
              <CollegeMark college={college} large />
              <div>
                <h1 className="pf-h1">{college.name}</h1>
                <p className="pf-muted">
                  Tenant ID {college.id} · schema <span className="pf-mono">{college.code}</span>
                  {college.created_on ? ` · added ${college.created_on}` : ""}
                </p>
              </div>
            </div>
            <StatusBadge active={college.is_active} />
          </div>

          <div className="pf-stats pf-stats-4">
            <Stat label="Students" value={college.counts.students} />
            <Stat label="Teachers" value={college.counts.teachers} />
            <Stat label="Parents" value={college.counts.parents} />
            <Stat label="Departments" value={college.counts.departments} />
          </div>

          <div className="pf-split">
            <div className="pf-stack">
              <section className="pf-card">
                <h2 className="pf-h2">Address</h2>
                {college.domains.map((d) => (
                  <p key={d}><a href={collegeUrl(d)} target="_blank" rel="noreferrer">{d}</a></p>
                ))}
              </section>

              <section className="pf-card">
                <h2 className="pf-h2">Logo</h2>
                <p className="pf-muted">
                  Shown on the college's sign-in page. PNG, JPEG or WebP, up to 2 MB; it is resized to fit 512 × 512.
                </p>
                {college.logo_version
                  ? <img className="pf-logo-preview" src={logoUrl(college)} alt={`${college.name} logo`} />
                  : <p className="pf-muted">No logo yet. The sign-in page shows the college name only.</p>}
                <div className="pf-actions pf-actions-start">
                  <label className={`pf-btn pf-btn-ghost pf-file${busy ? " pf-disabled" : ""}`}>
                    {college.logo_version ? "Replace logo" : "Upload logo"}
                    <input type="file" accept="image/png,image/jpeg,image/webp" onChange={uploadLogo} disabled={busy} />
                  </label>
                  {college.logo_version && (
                    <button type="button" className="pf-btn pf-btn-ghost" onClick={removeLogo} disabled={busy}>
                      Remove
                    </button>
                  )}
                </div>
              </section>

              <section className="pf-card">
                <h2 className="pf-h2">College admins</h2>
                <p className="pf-muted">{college.admins.length ? college.admins.join(", ") : "No admin yet."}</p>
                <form className="pf-grid2" onSubmit={resetPassword}>
                  <label className="pf-field">
                    <span>Admin username</span>
                    <select
                      value={reset.username}
                      onChange={(e) => setReset((r) => ({ ...r, username: e.target.value }))}
                      required
                    >
                      <option value="">Choose…</option>
                      {college.admins.map((a) => <option key={a} value={a}>{a}</option>)}
                    </select>
                  </label>
                  <label className="pf-field">
                    <span>New password</span>
                    <input
                      type="password"
                      value={reset.new_password}
                      onChange={(e) => setReset((r) => ({ ...r, new_password: e.target.value }))}
                      autoComplete="new-password"
                      required
                    />
                  </label>
                  <div className="pf-actions pf-span2">
                    <button type="submit" className="pf-btn pf-btn-ghost" disabled={busy || !college.admins.length}>
                      Reset admin password
                    </button>
                  </div>
                </form>
                <small className="pf-muted">The admin is asked to choose their own password at the next sign-in.</small>
              </section>
            </div>

            <aside className="pf-card pf-aside">
              <h2 className="pf-h2">Access</h2>
              <p className="pf-muted">
                {college.is_active
                  ? "This college is active. Its users can sign in at its address."
                  : "This college is switched off. Its users cannot sign in. All its data is kept."}
              </p>
              <button
                type="button"
                className={`pf-btn ${college.is_active ? "pf-btn-danger" : "pf-btn-primary"} pf-wide`}
                onClick={switchCollege}
                disabled={busy}
              >
                {college.is_active ? "Switch off college" : "Switch on college"}
              </button>

              {/* PHASE 3: status only - KB Technosoft never sees a college's keys */}
              <h2 className="pf-h2 pf-gap-top">Online payments</h2>
              <p><PaymentsBadge status={college.online_payments} /></p>
              <p className="pf-muted">
                {college.online_payments?.configured
                  ? `Fees are paid into this college's own Razorpay account${college.online_payments.webhook ? "." : ". The webhook secret is not saved yet."}`
                  : "The college admin has not saved the college's Razorpay keys yet (Fees → Online payments). Students can't pay online until then."}
              </p>
            </aside>
          </div>
        </>
      )}
    </>
  );
}

// ---------------------------------------------------------------- small pieces
// COLLEGE LOGO (public image; ?v= changes whenever the logo changes)
const logoUrl = (college) => `${API_BASE_URL}platform/colleges/${college.id}/logo/?v=${college.logo_version}`;

function CollegeMark({ college, large }) {
  if (college.logo_version) {
    return <img className={`pf-cmark${large ? " pf-cmark-lg" : ""}`} src={logoUrl(college)} alt="" />;
  }
  return (
    <span className={`pf-initials${large ? " pf-initials-lg" : ""}`} aria-hidden="true">
      {college.code.slice(0, 3).toUpperCase()}
    </span>
  );
}

function Stat({ label, value, tone }) {
  return (
    <div className="pf-card pf-stat">
      <span className="pf-muted">{label}</span>
      <span className={`pf-stat-value ${tone ? `pf-tone-${tone}` : ""}`}>{value}</span>
    </div>
  );
}

// PHASE 3: has the college saved its own Razorpay keys? (never the keys themselves)
function PaymentsBadge({ status }) {
  if (!status?.configured) return <span className="pf-badge pf-badge-warn">Not set up</span>;
  return status.mode === "live"
    ? <span className="pf-badge pf-badge-ok">Live</span>
    : <span className="pf-badge pf-badge-test">Test mode</span>;
}

function StatusBadge({ active }) {
  return <span className={`pf-badge ${active ? "pf-badge-ok" : "pf-badge-off"}`}>{active ? "Active" : "Switched off"}</span>;
}
