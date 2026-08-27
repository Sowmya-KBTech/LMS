import { useEffect, useState } from "react";

import Sidebar from "../../components/Sidebar";
import Navbar from "../../components/Navbar";

import API from "../../api";

import "../../App.css";

export default function StudentPlacement() {

  const [open, setOpen] = useState(false);

  // Which tab is showing. Set once the academics record loads: an unverified
  // student lands on the form, because that is what is blocking them. Anyone
  // else lands on drives, which is what they came for.
  const [tab, setTab] = useState(null);

  // ================= ACADEMICS FORM =================
  const [tenthPercent, setTenthPercent] = useState("");
  const [tenthBoard, setTenthBoard] = useState("");
  const [tenthYear, setTenthYear] = useState("");

  const [isLateral, setIsLateral] = useState(false);

  const [twelfthPercent, setTwelfthPercent] = useState("");
  const [twelfthBoard, setTwelfthBoard] = useState("");
  const [twelfthYear, setTwelfthYear] = useState("");

  const [diplomaPercent, setDiplomaPercent] = useState("");
  const [diplomaBranch, setDiplomaBranch] = useState("");
  const [diplomaYear, setDiplomaYear] = useState("");

  const [verified, setVerified] = useState(false);
  const [verifiedBy, setVerifiedBy] = useState("");
  const [verifiedAt, setVerifiedAt] = useState(null);
  const [exists, setExists] = useState(false);

  // ================= DRIVES =================
  const [drives, setDrives] = useState([]);
  const [standing, setStanding] = useState(null);
  const [eligibleCount, setEligibleCount] = useState(0);
  const [drivesLoading, setDrivesLoading] = useState(true);

  // ================= MY OFFERS =================
  const [myOffers, setMyOffers] = useState([]);
  const [acceptedCount, setAcceptedCount] = useState(0);
  const [offersLoading, setOffersLoading] = useState(true);
  const [decidingOn, setDecidingOn] = useState(null);

  // ================= APPLICATIONS =================
  // Which role the opt-out box is open for, and what has been typed in it.
  // Kept per-role rather than as one shared box, so opening a second one does
  // not carry the first one's reason across.
  const [optOutFor, setOptOutFor] = useState(null);
  const [optOutReason, setOptOutReason] = useState("");
  const [actingOn, setActingOn] = useState(null);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // ================= LOAD =================
  useEffect(() => {
    API.get("placement/my-academics/")
      .then((res) => {
        const d = res.data || {};

        setExists(!!d.exists);
        setVerified(!!d.verified);
        setVerifiedBy(d.verified_by_name || "");
        setVerifiedAt(d.verified_at || null);

        if (d.exists) {
          setTenthPercent(d.tenth_percent ?? "");
          setTenthBoard(d.tenth_board || "");
          setTenthYear(d.tenth_year ?? "");
          setIsLateral(!!d.is_lateral_entry);
          setTwelfthPercent(d.twelfth_percent ?? "");
          setTwelfthBoard(d.twelfth_board || "");
          setTwelfthYear(d.twelfth_year ?? "");
          setDiplomaPercent(d.diploma_percent ?? "");
          setDiplomaBranch(d.diploma_branch || "");
          setDiplomaYear(d.diploma_year ?? "");
        }

        // land on whichever tab is actually useful to this student
        setTab(d.verified ? "drives" : "details");
      })
      .catch((err) => {
        console.error("Academics load error:", err.response?.data || err);
        setError("Could not load your academic details.");
        setTab("details");
      })
      .finally(() => setLoading(false));

    loadDrives();

    loadOffers();
  }, []);

  const loadOffers = () => {
    setOffersLoading(true);

    API.get("placement/my-offers/")
      .then((res) => {
        const d = res.data || {};
        setMyOffers(d.results || []);
        setAcceptedCount(d.accepted || 0);
      })
      .catch((err) => console.error("Offers error:", err.response?.data || err))
      .finally(() => setOffersLoading(false));
  };

  // ================= ACCEPT / DECLINE =================
  // The decision is entirely the student's. Nothing is auto-declined when a
  // second offer is accepted -- holding two while deciding is a real thing to
  // do, and the placement report counts STUDENTS with an accepted offer, not
  // offer rows, so it cannot inflate the placed figure either way.
  const decideOffer = async (offer, newStatus) => {

    const verb = newStatus === "accepted" ? "Accept" : "Decline";
    if (!window.confirm(
      `${verb} the offer from ${offer.company_name}?`
    )) {
      return;
    }

    setError("");
    setNotice("");

    try {
      setDecidingOn(offer.id);

      await API.post(`placement/offers/${offer.id}/decide/`, {
        status: newStatus,
      });

      setNotice(
        newStatus === "accepted"
          ? `Accepted the offer from ${offer.company_name}.`
          : `Declined the offer from ${offer.company_name}.`
      );

      loadOffers();
      // an accepted offer can close further drives, depending on each role's
      // package cap -- so the drive list is now stale
      loadDrives();

    } catch (err) {
      console.error("Decide offer error:", err.response?.data || err);
      setError(err.response?.data?.detail || "Could not save your decision.");
    } finally {
      setDecidingOn(null);
    }
  };

  const loadDrives = () => {
    setDrivesLoading(true);

    API.get("placement/my-drives/")
      .then((res) => {
        const d = res.data || {};
        setDrives(d.results || []);
        setStanding(d.standing || null);
        // counted server-side across ROLES, not drives -- one drive can offer
        // several positions and a student may qualify for only some
        setEligibleCount(d.eligible_count || 0);
      })
      .catch((err) => console.error("Drives error:", err.response?.data || err))
      .finally(() => setDrivesLoading(false));
  };

  // ================= SAVE ACADEMICS =================
  const handleSave = async () => {

    setError("");
    setNotice("");

    if (tenthPercent === "" || Number(tenthPercent) <= 0) {
      return setError("Enter your 10th percentage.");
    }

    if (isLateral) {
      if (diplomaPercent === "" || Number(diplomaPercent) <= 0) {
        return setError("Enter your diploma percentage.");
      }
    } else {
      if (twelfthPercent === "" || Number(twelfthPercent) <= 0) {
        return setError("Enter your 12th percentage.");
      }
    }

    const payload = {
      tenth_percent: Number(tenthPercent),
      tenth_board: tenthBoard,
      tenth_year: tenthYear ? Number(tenthYear) : null,

      is_lateral_entry: isLateral,

      // The unused qualification is sent as null rather than omitted, so
      // switching lateral entry on or off clears the side that no longer
      // applies. Stale values there would be read by eligibility.
      twelfth_percent: isLateral ? null : Number(twelfthPercent),
      twelfth_board: isLateral ? "" : twelfthBoard,
      twelfth_year: isLateral || !twelfthYear ? null : Number(twelfthYear),

      diploma_percent: isLateral ? Number(diplomaPercent) : null,
      diploma_branch: isLateral ? diplomaBranch : "",
      diploma_year: isLateral && diplomaYear ? Number(diplomaYear) : null,
    };

    try {
      setSaving(true);

      const res = await API.put("placement/my-academics/", payload);
      const d = res.data || {};

      setExists(true);
      setVerified(!!d.verified);
      setVerifiedBy(d.verified_by_name || "");
      setVerifiedAt(d.verified_at || null);

      setNotice(
        d.verification_reset
          ? "Saved. Because you changed your marks, your coordinator needs to verify them again."
          : "Saved. Your coordinator will verify these details."
      );

      // eligibility depends on these values, so the drive list is now stale
      loadDrives();

    } catch (err) {
      const data = err.response?.data;
      console.error("Academics save error:", data);
      setError(
        data?.tenth_percent?.[0] ||
        data?.twelfth_percent?.[0] ||
        data?.diploma_percent?.[0] ||
        data?.detail ||
        "Could not save. Check the values and try again."
      );
    } finally {
      setSaving(false);
    }
  };

  // ================= APPLY / OPT OUT / WITHDRAW =================
  // One handler for all three. The SERVER re-checks eligibility and the
  // deadline -- this button appearing is not permission, and the page may
  // have been open for an hour.
  const decide = async (role, newStatus, reason = "") => {

    setError("");
    setNotice("");

    try {
      setActingOn(role.id);

      const payload = { status: newStatus };
      if (newStatus === "opted_out") {
        payload.opt_out_reason = reason;
      }

      await API.post(`placement/roles/${role.id}/apply/`, payload);

      setOptOutFor(null);
      setOptOutReason("");

      setNotice(
        newStatus === "applied"
          ? `Applied for ${role.title}.`
          : newStatus === "opted_out"
          ? `Noted — you are not interested in ${role.title}.`
          : `Withdrawn from ${role.title}.`
      );

      // refetch rather than patching locally: the server decides the final
      // state, and a local guess could disagree with it
      loadDrives();

    } catch (err) {
      const data = err.response?.data;
      console.error("Apply error:", data);

      // the API returns the blockers when it refuses -- show them, since they
      // are the only thing that tells the student what changed
      const blockers = data?.blockers?.length
        ? ` ${data.blockers.join(" ")}`
        : "";

      setError(
        (data?.detail || data?.opt_out_reason?.[0] || "Could not save that.") +
        blockers
      );
    } finally {
      setActingOn(null);
    }
  };

  // Counted from the roles already on screen rather than fetched separately:
  // one source, so the number cannot disagree with the cards below it.
  const appliedCount = drives.reduce(
    (n, d) =>
      n + (d.job_roles || []).filter(
        (r) => r.application?.status === "applied"
      ).length,
    0
  );

  const fmtDeadline = (value) =>
    value ? new Date(value).toLocaleString() : "No deadline set";

  // A drive is listed if ANY of its roles is open to this student, but every
  // role is shown either way -- a student needs to see the role they cannot
  // reach as well as the one they can.
  const withEligible = drives.filter((d) => d.any_eligible);
  const withoutEligible = drives.filter((d) => !d.any_eligible);

  // ================= ONE ROLE =================
  const renderRole = (role) => {

    // The student's own decision on this role, sent by the server. Applied,
    // opted out, withdrawn -- or null, meaning they have not answered, which
    // is a real state and not an error.
    const app = role.application;
    const decided = app?.status;
    const busy = actingOn === role.id;

    return (
      <div
        key={role.id}
        style={{
          borderLeft:
            decided === "applied"
              ? "4px solid #2563eb"
              : role.eligible
              ? "4px solid #16a34a"
              : "4px solid #cbd5e1",
          background:
            decided === "applied"
              ? "#eff6ff"
              : role.eligible
              ? "#f0fdf4"
              : "#f8fafc",
          borderRadius: "6px",
          padding: "10px 12px",
          marginTop: "8px",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: "12px",
            flexWrap: "wrap",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <p style={{ margin: 0, fontWeight: 600 }}>{role.title}</p>
            <p
              style={{
                margin: "3px 0 0",
                fontSize: "13px",
                color: role.eligible ? "#166534" : "#64748b",
              }}
            >
              {role.package_lpa ? `${role.package_lpa} LPA` : "Package not stated"}
              {role.job_location ? ` · ${role.job_location}` : ""}
              {role.openings ? ` · ${role.openings} openings` : ""}
            </p>
            {role.bond_details && (
              <p style={{ margin: "3px 0 0", fontSize: "12.5px", color: "#64748b" }}>
                Bond: {role.bond_details}
              </p>
            )}
          </div>

          {/* ---------- ACTIONS ---------- */}
          <div className="action-buttons">

            {decided === "applied" && (
              <>
                <span
                  style={{
                    fontSize: "13px",
                    color: "#1d4ed8",
                    fontWeight: 600,
                    alignSelf: "center",
                  }}
                >
                  Applied
                </span>
                {role.is_open && (
                  <button
                    className="btn-delete"
                    onClick={() => decide(role, "withdrawn")}
                    disabled={busy}
                  >
                    {busy ? "..." : "Withdraw"}
                  </button>
                )}
              </>
            )}

            {decided === "opted_out" && (
              <>
                <span
                  style={{ fontSize: "13px", color: "#64748b", alignSelf: "center" }}
                >
                  Not interested
                </span>
                {role.eligible && role.is_open && (
                  <button
                    className="btn-edit"
                    onClick={() => decide(role, "applied")}
                    disabled={busy}
                  >
                    Changed my mind
                  </button>
                )}
              </>
            )}

            {decided === "withdrawn" && (
              <>
                <span
                  style={{ fontSize: "13px", color: "#92400e", alignSelf: "center" }}
                >
                  Withdrawn
                </span>
                {role.eligible && role.is_open && (
                  <button
                    className="btn-edit"
                    onClick={() => decide(role, "applied")}
                    disabled={busy}
                  >
                    Apply again
                  </button>
                )}
              </>
            )}

            {/* Undecided. "Not interested" is offered even when the student
                is NOT eligible -- otherwise they sit in the placement cell's
                "no response" list forever with no way to answer. */}
            {!decided && (
              <>
                {role.eligible && role.is_open && (
                  <button
                    className="btn-primary"
                    onClick={() => decide(role, "applied")}
                    disabled={busy}
                  >
                    {busy ? "..." : "Apply"}
                  </button>
                )}
                {role.is_open && (
                  <button
                    className="btn-edit"
                    onClick={() => {
                      setOptOutFor(role.id);
                      setOptOutReason("");
                    }}
                    disabled={busy}
                  >
                    Not interested
                  </button>
                )}
                {!role.is_open && (
                  <span
                    style={{ fontSize: "13px", color: "#64748b", alignSelf: "center" }}
                  >
                    Closed
                  </span>
                )}
              </>
            )}

          </div>
        </div>

        {/* ---------- OPT-OUT REASON ---------- */}
        {optOutFor === role.id && (
          <div
            style={{
              marginTop: "10px",
              paddingTop: "10px",
              borderTop: "1px solid #e2e8f0",
            }}
          >
            <p style={{ margin: "0 0 6px", fontSize: "13px", fontWeight: 600 }}>
              Why are you not interested?
            </p>
            <p style={{ margin: "0 0 8px", fontSize: "12.5px", color: "#64748b" }}>
              Your coordinator sees this. A reason is required.
            </p>

            <div className="form-grid form-grid--row">
              <input
                placeholder="e.g. Higher studies, location, already placed"
                value={optOutReason}
                onChange={(e) => setOptOutReason(e.target.value)}
              />
              <button
                className="btn-primary"
                onClick={() => {
                  if (!optOutReason.trim()) {
                    return alert("Please give a reason");
                  }
                  decide(role, "opted_out", optOutReason.trim());
                }}
                disabled={busy}
              >
                {busy ? "Saving..." : "Confirm"}
              </button>
              <button
                className="btn-edit"
                onClick={() => {
                  setOptOutFor(null);
                  setOptOutReason("");
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* ---------- WHY NOT ---------- */}
        {!role.eligible && !decided && role.blockers?.length > 0 && (
          <div
            style={{
              marginTop: "8px",
              paddingTop: "8px",
              borderTop: "1px solid #e2e8f0",
            }}
          >
            <p
              style={{
                margin: "0 0 3px",
                fontSize: "12.5px",
                color: "#92400e",
                fontWeight: 600,
              }}
            >
              Why you cannot apply for this role
            </p>
            {role.blockers.map((b) => (
              <p
                key={b}
                style={{ margin: "2px 0 0", fontSize: "12.5px", color: "#64748b" }}
              >
                · {b}
              </p>
            ))}
          </div>
        )}

        {/* ---------- THEIR REASON ---------- */}
        {decided === "opted_out" && app?.opt_out_reason && (
          <p style={{ margin: "8px 0 0", fontSize: "12.5px", color: "#64748b" }}>
            Your reason: {app.opt_out_reason}
          </p>
        )}
      </div>
    );
  };

  // ================= ONE DRIVE =================
  const renderDrive = (d) => (
    <div
      key={d.id}
      style={{
        border: "1px solid #e2e8f0",
        borderRadius: "8px",
        padding: "14px",
        marginBottom: "12px",
      }}
    >
      <p style={{ margin: 0, fontWeight: 600, fontSize: "15px" }}>
        {d.company_name}
        {d.title ? ` — ${d.title}` : ""}
      </p>

      <p style={{ margin: "4px 0 0", fontSize: "13px", color: "#64748b" }}>
        {d.company_category || "—"}
        {" · Closes "}
        {fmtDeadline(d.application_deadline)}
      </p>

      {d.rounds?.length > 0 && (
        <p style={{ margin: "6px 0 0", fontSize: "13px", color: "#64748b" }}>
          Rounds: {d.rounds.map((r) => r.name).join(" → ")}
        </p>
      )}

      <p
        style={{
          margin: "10px 0 0",
          fontSize: "12px",
          letterSpacing: "0.04em",
          color: "#94a3b8",
        }}
      >
        {d.job_roles.length === 1
          ? "1 ROLE"
          : `${d.job_roles.length} ROLES`}
      </p>

      {/* Eligible roles first, so what a student can act on is at the top */}
      {d.job_roles
        .slice()
        .sort((a, b) => Number(b.eligible) - Number(a.eligible))
        .map(renderRole)}
    </div>
  );

  return (
    <div className="app">

      <Navbar setOpen={setOpen} />

      <div className="layout">

        <Sidebar open={open} setOpen={setOpen} />

        <div className="main">

          <div className="content">

            {/* ================= HEADER ================= */}
            <div className="header-box">
              <h2>Placement</h2>
              <p>
                {standing?.passing_year
                  ? `Passing out ${standing.passing_year}.`
                  : "Your drives and academic details."}
              </p>
            </div>

            {/* ================= TABS ================= */}
            <div className="card">
              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                <button
                  className={tab === "drives" ? "btn-primary" : "btn-edit"}
                  onClick={() => setTab("drives")}
                >
                  Available drives{drivesLoading ? "" : ` (${eligibleCount})`}
                </button>
                <button
                  className={tab === "details" ? "btn-primary" : "btn-edit"}
                  onClick={() => setTab("details")}
                >
                  My academic details
                  {!loading && !verified ? " •" : ""}
                </button>
                <button
                  className={tab === "offers" ? "btn-primary" : "btn-edit"}
                  onClick={() => setTab("offers")}
                >
                  My offers{offersLoading ? "" : ` (${myOffers.length})`}
                </button>
              </div>
            </div>

            {/* ================= MESSAGES ================= */}
            {error && (
              <div
                className="card"
                style={{ borderLeft: "4px solid #dc2626", color: "#991b1b" }}
              >
                {error}
              </div>
            )}

            {notice && (
              <div
                className="card"
                style={{ borderLeft: "4px solid #16a34a", color: "#166534" }}
              >
                {notice}
              </div>
            )}

            {/* ========================================================= */}
            {/* ================= DRIVES TAB ============================ */}
            {/* ========================================================= */}
            {tab === "drives" && (
              <>

                {/* ---------- STANDING ---------- */}
                <div className="card">
                  <h3>Where you stand</h3>
                  <div style={{ display: "flex", gap: "24px", flexWrap: "wrap" }}>
                    <div>
                      <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                        Roles you can apply for
                      </p>
                      <p style={{ margin: "4px 0 0", fontSize: "22px", fontWeight: 600 }}>
                        {drivesLoading ? "—" : eligibleCount}
                      </p>
                    </div>
                    <div>
                      <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                        Applied
                      </p>
                      <p style={{ margin: "4px 0 0", fontSize: "22px", fontWeight: 600 }}>
                        {drivesLoading ? "—" : appliedCount}
                      </p>
                    </div>
                    <div>
                      <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                        CGPA
                      </p>
                      <p style={{ margin: "4px 0 0", fontSize: "22px", fontWeight: 600 }}>
                        {standing?.cgpa ?? "—"}
                      </p>
                    </div>
                    <div>
                      <p style={{ margin: 0, fontSize: "13px", color: "#64748b" }}>
                        Arrears
                      </p>
                      <p style={{ margin: "4px 0 0", fontSize: "22px", fontWeight: 600 }}>
                        {standing?.arrears ?? "—"}
                      </p>
                    </div>
                  </div>

                  {standing?.cgpa === null && standing?.cgpa_reason && (
                    <p style={{ margin: "12px 0 0", fontSize: "13px", color: "#92400e" }}>
                      {standing.cgpa_reason === "no_results"
                        ? "Your CGPA will show once your results are published."
                        : "Your CGPA is not available — please contact the office."}
                    </p>
                  )}
                </div>

                {/* ---------- DRIVES WITH AN ELIGIBLE ROLE ---------- */}
                {!drivesLoading && withEligible.length > 0 && (
                  <div className="card">
                    <h3>Open to you ({withEligible.length})</h3>
                    <p style={{ margin: "0 0 12px", fontSize: "13px", color: "#64748b" }}>
                      You qualify for at least one role in each of these.
                    </p>
                    {withEligible.map(renderDrive)}
                  </div>
                )}

                {/* ---------- DRIVES WITH NONE ---------- */}
                {!drivesLoading && withoutEligible.length > 0 && (
                  <div className="card">
                    <h3>Not eligible yet ({withoutEligible.length})</h3>
                    <p style={{ margin: "0 0 12px", fontSize: "13px", color: "#64748b" }}>
                      Shown so you know what is open and what is holding you
                      back.
                    </p>
                    {withoutEligible.map(renderDrive)}
                  </div>
                )}

                {/* ---------- EMPTY ---------- */}
                {!drivesLoading && drives.length === 0 && (
                  <div className="card">
                    <p style={{ margin: 0 }}>
                      No drives have been published yet. Check back during
                      placement season.
                    </p>
                  </div>
                )}

                {drivesLoading && (
                  <div className="card">
                    <p style={{ margin: 0 }}>Loading drives...</p>
                  </div>
                )}

              </>
            )}

            {/* ========================================================= */}
            {/* ================= DETAILS TAB =========================== */}
            {/* ========================================================= */}
            {tab === "details" && (
              <>

                {/* ---------- STATUS ---------- */}
                {!loading && (
                  <div
                    className="card"
                    style={{
                      borderLeft: verified
                        ? "4px solid #16a34a"
                        : exists
                        ? "4px solid #ca8a04"
                        : "4px solid #64748b",
                    }}
                  >
                    {verified ? (
                      <>
                        <strong>Verified</strong>
                        <p style={{ margin: "6px 0 0" }}>
                          Checked by {verifiedBy || "your coordinator"}
                          {verifiedAt
                            ? ` on ${new Date(verifiedAt).toLocaleDateString()}`
                            : ""}
                          . You can apply for roles you are eligible for.
                        </p>
                      </>
                    ) : exists ? (
                      <>
                        <strong>Waiting for verification</strong>
                        <p style={{ margin: "6px 0 0" }}>
                          Your coordinator needs to check these marks before you
                          can apply for anything.
                        </p>
                      </>
                    ) : (
                      <>
                        <strong>Not filled in yet</strong>
                        <p style={{ margin: "6px 0 0" }}>
                          Add your 10th and 12th marks below. Without them you
                          cannot apply for any role.
                        </p>
                      </>
                    )}
                  </div>
                )}

                {/* ---------- 10TH ---------- */}
                <div className="card">
                  <h3>10th Standard</h3>

                  {loading ? (
                    <p>Loading...</p>
                  ) : (
                    <div className="form-grid form-grid--row">
                      <input
                        type="number"
                        min="1"
                        max="100"
                        step="0.01"
                        placeholder="Percentage *"
                        value={tenthPercent}
                        onChange={(e) => setTenthPercent(e.target.value)}
                      />
                      <input
                        placeholder="Board (State Board / CBSE / ICSE)"
                        value={tenthBoard}
                        onChange={(e) => setTenthBoard(e.target.value)}
                      />
                      <input
                        type="number"
                        placeholder="Year of passing"
                        value={tenthYear}
                        onChange={(e) => setTenthYear(e.target.value)}
                      />
                    </div>
                  )}
                </div>

                {/* ---------- ENTRY TYPE ---------- */}
                {!loading && (
                  <div className="card">
                    <h3>How did you join?</h3>

                    <label
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "8px",
                        fontSize: "14px",
                        color: "#334155",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={isLateral}
                        onChange={(e) => setIsLateral(e.target.checked)}
                      />
                      I joined in 2nd year with a diploma (lateral entry)
                    </label>

                    <p style={{ margin: "8px 0 0", fontSize: "13px", color: "#64748b" }}>
                      {isLateral
                        ? "Fill in your diploma marks below. 12th is not needed."
                        : "Fill in your 12th marks below."}
                    </p>
                  </div>
                )}

                {/* ---------- 12TH ---------- */}
                {!loading && !isLateral && (
                  <div className="card">
                    <h3>12th Standard</h3>
                    <div className="form-grid form-grid--row">
                      <input
                        type="number"
                        min="1"
                        max="100"
                        step="0.01"
                        placeholder="Percentage *"
                        value={twelfthPercent}
                        onChange={(e) => setTwelfthPercent(e.target.value)}
                      />
                      <input
                        placeholder="Board (State Board / CBSE / ICSE)"
                        value={twelfthBoard}
                        onChange={(e) => setTwelfthBoard(e.target.value)}
                      />
                      <input
                        type="number"
                        placeholder="Year of passing"
                        value={twelfthYear}
                        onChange={(e) => setTwelfthYear(e.target.value)}
                      />
                    </div>
                  </div>
                )}

                {/* ---------- DIPLOMA ---------- */}
                {!loading && isLateral && (
                  <div className="card">
                    <h3>Diploma</h3>
                    <div className="form-grid form-grid--row">
                      <input
                        type="number"
                        min="1"
                        max="100"
                        step="0.01"
                        placeholder="Percentage *"
                        value={diplomaPercent}
                        onChange={(e) => setDiplomaPercent(e.target.value)}
                      />
                      <input
                        placeholder="Branch"
                        value={diplomaBranch}
                        onChange={(e) => setDiplomaBranch(e.target.value)}
                      />
                      <input
                        type="number"
                        placeholder="Year of passing"
                        value={diplomaYear}
                        onChange={(e) => setDiplomaYear(e.target.value)}
                      />
                    </div>
                  </div>
                )}

                {/* ---------- SAVE ---------- */}
                {!loading && (
                  <div className="card">
                    {verified && (
                      <p style={{ margin: "0 0 12px", fontSize: "13px", color: "#92400e" }}>
                        These marks are already verified. If you change
                        anything, your coordinator will need to verify them
                        again.
                      </p>
                    )}

                    <button
                      className="btn-primary"
                      onClick={handleSave}
                      disabled={saving}
                    >
                      {saving ? "Saving..." : exists ? "Update details" : "Save details"}
                    </button>
                  </div>
                )}

              </>
            )}


            {/* ========================================================= */}
            {/* ================= OFFERS TAB ============================ */}
            {/* ========================================================= */}
            {tab === "offers" && (
              <div className="card">

                <h3>My offers</h3>

                {offersLoading ? (
                  <p>Loading...</p>
                ) : myOffers.length === 0 ? (
                  <p style={{ margin: 0 }}>
                    No offers yet. They appear here once a company selects you
                    and your placement officer records it.
                  </p>
                ) : (
                  <>
                    <p style={{ margin: "0 0 14px", fontSize: "13px", color: "#64748b" }}>
                      {myOffers.length} offer{myOffers.length === 1 ? "" : "s"}
                      {acceptedCount > 0
                        ? ` · ${acceptedCount} accepted`
                        : " · none accepted yet"}
                      . You choose which to accept — nothing is decided for you.
                    </p>

                    {/* ONE list, not tabs by status. A student with three
                        offers is COMPARING them, and splitting accepted from
                        waiting would hide the comparison they came to make. */}
                    {myOffers.map((o) => {
                      const busy = decidingOn === o.id;

                      return (
                        <div
                          key={o.id}
                          style={{
                            borderLeft:
                              o.status === "accepted"
                                ? "4px solid #16a34a"
                                : o.status === "declined"
                                ? "4px solid #cbd5e1"
                                : "4px solid #ca8a04",
                            background:
                              o.status === "accepted"
                                ? "#f0fdf4"
                                : o.status === "declined"
                                ? "#f8fafc"
                                : "#fffbeb",
                            borderRadius: "6px",
                            padding: "12px 14px",
                            marginBottom: "10px",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "flex-start",
                              gap: "12px",
                              flexWrap: "wrap",
                            }}
                          >
                            <div style={{ minWidth: 0 }}>
                              <p style={{ margin: 0, fontWeight: 600, fontSize: "15px" }}>
                                {o.company_name} — {o.role_title}
                              </p>
                              <p style={{ margin: "4px 0 0", fontSize: "13px", color: "#64748b" }}>
                                {o.package_lpa ? `${o.package_lpa} LPA` : "Package not stated"}
                                {o.job_location ? ` · ${o.job_location}` : ""}
                                {o.joining_date ? ` · joining ${o.joining_date}` : ""}
                              </p>
                              {o.remarks && (
                                <p style={{ margin: "4px 0 0", fontSize: "12.5px", color: "#64748b" }}>
                                  {o.remarks}
                                </p>
                              )}
                              <p style={{ margin: "6px 0 0", fontSize: "12.5px", color: "#64748b" }}>
                                Offered on {o.offered_on}
                                {o.decided_at
                                  ? ` · you answered on ${new Date(o.decided_at).toLocaleDateString()}`
                                  : ""}
                              </p>
                            </div>

                            <div className="action-buttons">
                              {o.status === "offered" && (
                                <>
                                  <button
                                    className="btn-primary"
                                    onClick={() => decideOffer(o, "accepted")}
                                    disabled={busy}
                                  >
                                    {busy ? "..." : "Accept"}
                                  </button>
                                  <button
                                    className="btn-delete"
                                    onClick={() => decideOffer(o, "declined")}
                                    disabled={busy}
                                  >
                                    Decline
                                  </button>
                                </>
                              )}

                              {o.status === "accepted" && (
                                <>
                                  <span
                                    style={{
                                      fontSize: "13px",
                                      color: "#166534",
                                      fontWeight: 600,
                                      alignSelf: "center",
                                    }}
                                  >
                                    Accepted
                                  </span>
                                  {/* Changing their mind is allowed. A student
                                      who accepts and then gets a better offer
                                      should not have to ask the office. */}
                                  <button
                                    className="btn-edit"
                                    onClick={() => decideOffer(o, "declined")}
                                    disabled={busy}
                                  >
                                    Decline instead
                                  </button>
                                </>
                              )}

                              {o.status === "declined" && (
                                <>
                                  <span
                                    style={{
                                      fontSize: "13px",
                                      color: "#64748b",
                                      alignSelf: "center",
                                    }}
                                  >
                                    Declined
                                  </span>
                                  <button
                                    className="btn-edit"
                                    onClick={() => decideOffer(o, "accepted")}
                                    disabled={busy}
                                  >
                                    Accept instead
                                  </button>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}

                    <p style={{ margin: "14px 0 0", fontSize: "13px", color: "#64748b" }}>
                      Accepting an offer may close further drives, depending on
                      the package — check the Available drives tab afterwards.
                    </p>
                  </>
                )}

              </div>
            )}

          </div>

        </div>

      </div>

    </div>
  );
}