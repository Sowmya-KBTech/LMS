import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Icon from "../components/Icon";
import kbLogo from "../assets/kb-logo.png";
import { clearRoleFlags } from "../components/useRoleFlags";
import { API_BASE_URL } from "../apiBase";   // SAAS PHASE 2: this college's API
import { SIGNIN_NOTE_KEY } from "../api";

// Where a user lands after signing in is decided by their account
// (RoleRedirect in App.jsx), so there is no role picker here.
const FEATURES = [
  { icon: "calendar", title: "Attendance & timetable", text: "Period-wise attendance, auto-built timetables and substitutions in one place." },
  { icon: "exam", title: "Internals, results & hall tickets", text: "IA marks, semester results and revaluation — visible to students and parents." },
  { icon: "rupee", title: "Fees & placement", text: "Online fee payment, receipts, drives, applications and offers." },
];

function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  // SAAS PHASE 2: which college this address belongs to (null until known)
  const [college, setCollege] = useState(null);

  const navigate = useNavigate();

  // PHASE 5 PART 4: why we were sent here (signed out, password changed...)
  useEffect(() => {
    try {
      const why = sessionStorage.getItem(SIGNIN_NOTE_KEY);
      if (why) {
        sessionStorage.removeItem(SIGNIN_NOTE_KEY);
        setNote(why);
      }
    } catch { /* private mode */ }
  }, []);

  useEffect(() => {
    fetch(`${API_BASE_URL}college/`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setCollege(data))
      .catch(() => setCollege(null));   // server down: the sign-in error explains it
  }, []);

  const onPlatform = college?.platform === true;
  // PLATFORM CONSOLE: KB Technosoft can switch a college off
  const switchedOff = college?.active === false;

  const handleLogin = async (e) => {
    if (e) e.preventDefault();
    setError("");
    setNote("");

    if (!username || !password) {
      setError("Enter your username and password to continue.");
      return;
    }

    setLoading(true);

    try {
      // credentials: "include" lets the browser KEEP the session cookie Django
      // sets on login. The JWT saved below covers API calls, but files are not
      // fetched by JavaScript -- a photo is an <img src="/media/...">, a resume
      // is a plain link -- and those requests carry no token. The session
      // cookie is the only thing that can prove who is asking for a file.
      //
      // This uses fetch rather than the shared API instance, so axios's
      // withCredentials does not apply and has to be set here explicitly.
      //
      // The host must be localhost, matching the Vite dev server. A cookie set
      // for 127.0.0.1 is NOT sent by a page served from localhost -- browsers
      // treat the two as different sites, so the cookie would be discarded.
      const response = await fetch(
        `${API_BASE_URL}users/login/`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ username, password }),
        }
      );

      const data = await response.json();

      if (response.ok) {
        // SAVE TOKEN
        localStorage.setItem("token", data.access);
        localStorage.setItem("user", JSON.stringify(data));
        clearRoleFlags(); // a new user — forget the previous user's HOD/tutor flags

        // first-login users must set a new password before anything else
        if (data.must_change_password === true) {
          navigate("/change-password");
          return;
        }

        // ================= WHERE TO LAND =================
        // Decided in ONE place: RoleRedirect in App.jsx.
        // Adding a new role means editing RoleRedirect only.
        navigate("/home");
      } else {
        setError(data.error || "That username and password don't match. Check them and try again.");
      }
    } catch (err) {
      console.log(err);
      setError("Can't reach the server. Check your connection and try again.");
    }

    setLoading(false);
  };

  const officeNote = () =>
    setNote("Your college admin office can reset your password or activate your account.");

  return (
    <div className="kb-auth">
      {/* ---------- left: brand panel ---------- */}
      <aside className="kb-auth-panel">
        <div className="kb-auth-brand">
          <img src={kbLogo} alt="KB Tech logo" />
          <div>
            <b>KB Tech Campus</b>
            <small>Campus management for engineering colleges</small>
          </div>
        </div>

        <div className="kb-auth-pitch">
          <h1>One campus.<br />Every role.<br /><span>One sign-in.</span></h1>
          <ul>
            {FEATURES.map((f) => (
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
        <form className="kb-auth-form" onSubmit={handleLogin} noValidate>
          <div className="kb-auth-mbrand">
            <img src={kbLogo} alt="" />
            <b>KB Tech Campus</b>
          </div>

          <div>
            <h2>Welcome back</h2>
            {college && !onPlatform && (
              <div className="kb-college-id">
                {/* COLLEGE LOGO: set by KB Technosoft in the platform console */}
                {college.logo_version && (
                  <img
                    className="kb-college-logo"
                    src={`${API_BASE_URL}college/logo/?v=${college.logo_version}`}
                    alt=""
                  />
                )}
                <p className="kb-lede"><b>{college.name}</b></p>
              </div>
            )}
            <p className="kb-lede">Sign in with the username issued by your college. We'll take you to the right dashboard.</p>
          </div>

          {switchedOff && (
            <div className="kb-auth-note" role="alert">
              This college's access is switched off. Please contact KB Technosoft.
            </div>
          )}

          {onPlatform && (
            <div className="kb-auth-note" role="status">
              This is the KB Tech Campus platform address. Open your college's own
              address to sign in, for example <b>abc.localhost:5173</b>.
            </div>
          )}

          <label className="kb-field">
            <span>Username</span>
            <div className="kb-ifield">
              <Icon name="user" />
              <input
                className="kb-input"
                name="username"
                autoComplete="username"
                placeholder="2021CSE045"
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

          <div className="kb-auth-row">
            <span />
            <button type="button" className="kb-linkbtn" onClick={officeNote}>Forgot password?</button>
          </div>

          {error && <div className="kb-err" role="alert">{error}</div>}
          {note && <div className="kb-auth-note" role="status">{note}</div>}

          <button className="kb-btn kb-btn--primary kb-cta" type="submit" disabled={loading || onPlatform || switchedOff}>
            {loading ? "Signing in…" : "Sign in"}
            {!loading && <Icon name="arrowRight" />}
          </button>

          <div className="kb-auth-info">
            <Icon name="help" />
            <span>Students, faculty, parents and staff all sign in here.</span>
          </div>
        </form>
      </main>
    </div>
  );
}

export default Login;
