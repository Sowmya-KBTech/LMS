import { useEffect, useState } from "react";

import API from "../../api";

const COURSES_URL = "/courses/";
const YEARS_URL = "/years/";

const SEMESTERS = Array.from({ length: 8 }, (_, i) => i + 1);

// Monday to Friday. Saturday was removed from TimetableEntry.day_of_week, so
// the serializer now rejects day_of_week=5 outright.
//
// This array is the only place the week is defined in this file: the grid
// header, the break row's colSpan, and paintForActivity's free/blocked map all
// read it. Adding a day back is a one-line change here plus the model choice.
const DAYS = [
  { value: 0, label: "Mon" },
  { value: 1, label: "Tue" },
  { value: 2, label: "Wed" },
  { value: 3, label: "Thu" },
  { value: 4, label: "Fri" },
];

const fmt = (t) => {
  if (!t) return "";
  const [h, m] = String(t).split(":");
  let hour = parseInt(h, 10);
  const ampm = hour >= 12 ? "PM" : "AM";
  hour = hour % 12 || 12;
  return `${hour}:${m} ${ampm}`;
};

const STATUS_STYLE = {
  draft:     { bg: "#ECECF0", fg: "#5D5A6B", bd: "#E7E7EC", label: "Draft" },
  submitted: { bg: "#fff7ed", fg: "#8A4B0A", bd: "#fed7aa", label: "Submitted — awaiting admin" },
  approved:  { bg: "#ecfdf5", fg: "#15803d", bd: "#bbf7d0", label: "Approved" },
  rejected:  { bg: "#fef2f2", fg: "#dc2626", bd: "#fecaca", label: "Rejected" },
};

export default function GridPanel({ goToPeriods, courseFilter = null }) {
  const isHodMode = !!(courseFilter && courseFilter.length);

  const [courses, setCourses] = useState([]);
  const [years, setYears] = useState([]);
  const [slots, setSlots] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [entries, setEntries] = useState([]);
  const [busy, setBusy] = useState({});

  // activities
  const [activityTypes, setActivityTypes] = useState([]);   // Library, Mentor, Sports…
  const [classActs, setClassActs] = useState([]);           // what THIS class has
  const [newAct, setNewAct] = useState("");
  const [showActs, setShowActs] = useState(false);

  const [sel, setSel] = useState({ course: "", year: "", semester: "" });
  const [room, setRoom] = useState("");

  const [error, setError] = useState("");
  const [popup, setPopup] = useState("");   // center modal: "teacher busy in [class]"
  const [hint, setHint] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState("");
  const [approval, setApproval] = useState(null);
  const [filling, setFilling] = useState(false);
  const [conflicts, setConflicts] = useState([]);

  // AUTO-FILL CHOICE pop-up (meeting point 1): ask what to allocate first
  const [autoOpen, setAutoOpen] = useState(false);
  const [autoPick, setAutoPick] = useState({ subjects: [], activities: [] });
  const [autoResult, setAutoResult] = useState(null); // { message, not_placed }

  // what's picked up: { type: "subject"|"activity", data: {...} }
  const [selected, setSelected] = useState(null);
  const [dragging, setDragging] = useState(null);

  // which empty cell is being typed into: "day_slotId", or null
  const [typing, setTyping] = useState(null);
  const [typeText, setTypeText] = useState("");
  const [freeCells, setFreeCells] = useState(null);
  const [blockedCells, setBlockedCells] = useState(null);

  const showToast = (msg) => {
    setToast(msg);
    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => setToast(""), 2200);
  };

  const classReady = sel.year && sel.semester;
  const locked = isHodMode && approval?.status === "submitted";
  const painting = blockedCells !== null;

  // ---------- initial loads ----------
  useEffect(() => {
    API.get(COURSES_URL).then((r) => setCourses(r.data || [])).catch(() => {});
    API.get("/timeslots/").then((r) => setSlots(r.data || [])).catch(() => {});
    API.get("/rooms/").then((r) => setRooms(r.data || [])).catch(() => {});
    API.get("/activity-types/").then((r) => setActivityTypes(r.data || [])).catch(() => {});
  }, []);

  const visibleCourses =
    courseFilter && courseFilter.length
      ? courses.filter((c) => courseFilter.map(String).includes(String(c.id)))
      : courses;

  useEffect(() => {
    if (courseFilter && courseFilter.length && visibleCourses.length === 1 && !sel.course) {
      setSel((s) => ({ ...s, course: String(visibleCourses[0].id) }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courses, courseFilter]);

  useEffect(() => {
    setYears([]);
    setSel((s) => ({ ...s, year: "", semester: "" }));
    if (!sel.course) return;
    API.get(`${YEARS_URL}?course=${sel.course}`)
      .then((r) => setYears(r.data || []))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel.course]);

  useEffect(() => {
    clearSelection();
    setConflicts([]);
    if (!classReady) {
      setApproval(null);
      setEntries([]);
      setAssignments([]);
      setClassActs([]);
      setBusy({});
      return;
    }
    loadClass();
    loadStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel.year, sel.semester]);

  // Year 2 has Semester 3 and 4 — not 1, not 7.
  const legalSemesters = (() => {
    const y = years.find((x) => String(x.id) === String(sel.year));
    if (!y) return SEMESTERS;
    const n = y.year_number;
    return SEMESTERS.filter((s) => s === n * 2 - 1 || s === n * 2);
  })();

  const loadClass = async () => {
    setLoading(true);
    setError("");
    const q = `year=${sel.year}&semester=${sel.semester}`;
    try {
      const [e, a, b, ca] = await Promise.all([
        API.get(`/timetable/?${q}`),
        API.get(`/timetable/options/?${q}`),
        API.get(`/timetable/busy/?${q}`).catch(() => ({ data: {} })),
        API.get(`/class-activities/?${q}`).catch(() => ({ data: [] })),
      ]);
      setEntries(e.data || []);
      setAssignments(a.data || []);
      setBusy(b.data || {});
      setClassActs(ca.data || []);
    } catch (err) {
      console.error("Load class error:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadStatus = async () => {
    if (!isHodMode) return;
    try {
      const r = await API.get(
        `/timetable/approval-status/?year=${sel.year}&semester=${sel.semester}`
      );
      setApproval(r.data || null);
    } catch {
      setApproval(null);
    }
  };

  const lookup = {};
  entries.forEach((e) => {
    lookup[`${e.day_of_week}_${e.time_slot}`] = e;
  });

  // ================================================================
  //  ACTIVITY CONFIG — set once per class, reused every regenerate
  // ================================================================
  const toggleActivity = async (type, on) => {
    setError("");
    try {
      if (on) {
        await API.post("/class-activities/", {
          activity: type.id,
          year: sel.year,
          semester: sel.semester,
          periods_per_week: 1,
        });
      } else {
        const mine = classActs.find((c) => c.activity === type.id);
        if (mine) await API.delete(`/class-activities/${mine.id}/`);
      }
      await loadClass();
    } catch {
      setError("Could not update that activity.");
    }
  };

  const setActivityHours = async (ca, n) => {
    try {
      await API.patch(`/class-activities/${ca.id}/`, {
        periods_per_week: Number(n) || 1,
      });
      await loadClass();
    } catch {
      setError("Could not change the periods.");
    }
  };

  // type your own — "Placement Training", "NSS", "Club Hour".
  // Subjects come from Faculty Allocation so you can't invent those.
  // Activities have no master list, so free text is right here.
  const addOwnActivity = async () => {
    const name = newAct.trim();
    if (!name) return;
    setError("");
    try {
      const r = await API.post("/activity-types/", {
        name,
        preferred_position: "any",
        colour: "#85839A",
      });
      setActivityTypes((list) => [...list, r.data]);
      await toggleActivity(r.data, true);
      setNewAct("");
    } catch (err) {
      setError(err?.response?.data?.name?.[0] || "Could not add that activity.");
    }
  };

  // ---- type straight into an empty cell ----
  // Goes through the SAME two models as the Activities box: an ActivityType the
  // college owns, and a ClassActivity saying this class uses it. So anything you
  // type here is immediately known to Auto-fill, the solver, the admin's Review
  // screen and the students' timetable. Typing is a faster door into the same
  // thing — not a second, parallel one.
  const placeTypedActivity = async (day, slotId, raw) => {
    const name = (raw || "").trim();
    if (!name) {
      setTyping(null);
      setTypeText("");
      return;
    }
    setError("");

    try {
      // 1) the activity type — reuse it if the college already has it,
      //    otherwise the unique-name constraint rejects the POST
      let type = activityTypes.find(
        (t) => t.name.trim().toLowerCase() === name.toLowerCase()
      );
      if (!type) {
        const r = await API.post("/activity-types/", {
          name,
          preferred_position: "any",
          colour: "#85839A",
        });
        type = r.data;
        setActivityTypes((list) => [...list, type]);
      }

      // 2) this class's use of it. If it already has one, widen its weekly
      //    target — otherwise this new cell would push it past its own limit
      //    and the chip would read "3 of 2 placed".
      let mine = classActs.find((c) => c.activity === type.id);
      if (!mine) {
        const r = await API.post("/class-activities/", {
          activity: type.id,
          year: sel.year,
          semester: sel.semester,
          periods_per_week: 1,
        });
        mine = r.data;
      } else if ((mine.placed || 0) + 1 > mine.periods_per_week) {
        const r = await API.patch(`/class-activities/${mine.id}/`, {
          periods_per_week: (mine.placed || 0) + 1,
        });
        mine = r.data;
      }

      // 3) the cell itself
      await API.post("/timetable/", {
        kind: "activity",
        assignment: null,
        class_activity: mine.id,
        day_of_week: day,
        time_slot: slotId,
        room: null,
      });

      await loadClass();
      await loadStatus();
      showToast(`✓ ${name} added`);
    } catch (err) {
      const data = err?.response?.data;
      setError(
        (Array.isArray(data) ? data[0] : data?.detail) ||
          data?.name?.[0] ||
          "Could not add that — there may be a clash."
      );
    } finally {
      setTyping(null);
      setTypeText("");
    }
  };

  // ================================================================
  //  PAINT — which cells can this thing use?
  // ================================================================
  const paintForSubject = async (a) => {
    try {
      const r = await API.post("/timetable/availability/", {
        assignment: a.id,
        year: sel.year,
        semester: sel.semester,
        room: room || null,
      });
      const blocked = new Map();
      (r.data.blocked || []).forEach((c) => blocked.set(`${c.day}_${c.slot}`, c.reason));
      setBlockedCells(blocked);
      setFreeCells(new Set((r.data.free || []).map((c) => `${c.day}_${c.slot}`)));

      const real = (r.data.blocked || []).find(
        (c) => !c.reason.startsWith("This class already")
      )?.reason;
      setHint(
        real
          ? `Grey slots: ${real}. Click a green slot to place ${a.subject}.`
          : `Click a green slot to place ${a.subject}.`
      );
    } catch {
      setBlockedCells(null);
      setFreeCells(null);
    }
  };

  // An activity with no teacher clashes with nobody — every empty cell of THIS
  // class is fair game. No server call needed.
  const paintForActivity = (ca) => {
    const blocked = new Map();
    const free = new Set();
    slots.forEach((s) => {
      if (s.is_break) return;
      DAYS.forEach((d) => {
        const key = `${d.value}_${s.id}`;
        if (lookup[key]) blocked.set(key, "This class already has something here");
        else free.add(key);
      });
    });

    setBlockedCells(blocked);
    setFreeCells(free);
    setHint(`Click any green slot to place ${ca.name}.`);
  };

  const clearSelection = () => {
    setSelected(null);
    setDragging(null);
    setBlockedCells(null);
    setFreeCells(null);
    setHint("");
  };

  const toggleSelectSubject = (a) => {
    setError("");
    if (selected?.type === "subject" && selected.data.id === a.id) return clearSelection();
    setSelected({ type: "subject", data: a });
    setDragging(null);
    paintForSubject(a);
  };

  const toggleSelectActivity = (ca) => {
    setError("");
    if (selected?.type === "activity" && selected.data.id === ca.id) return clearSelection();
    setSelected({ type: "activity", data: ca });
    setDragging(null);
    paintForActivity(ca);
  };

  const onDragStart = (a) => {
    setError("");
    setSelected(null);
    setDragging(a);
    paintForSubject(a);
  };

  const onDragEnd = () => {
    setDragging(null);
    if (!selected) { setBlockedCells(null); setFreeCells(null); setHint(""); }
  };

  // ================================================================
  //  PLACE — and if we refuse, SAY WHY (busy clashes -> center popup)
  // ================================================================
  const tryPlaceSubject = (day, slotId, a) => {
    const key = `${day}_${slotId}`;
    if (freeCells && !freeCells.has(key)) {
      const why = blockedCells?.get(key) || "that slot isn't available";
      // A "this class already has something here" is a mild bump — keep it in
      // the thin bar. A teacher/room clash names another class; that goes to
      // the center popup so it can't be missed.
      if (why.startsWith("This class already")) {
        setError(`Can't place ${a.subject} there — ${why}.`);
      } else {
        setPopup(`${a.subject} can't go here — ${why}.`);
      }
      clearSelection();
      return;
    }
    const done = entries.filter((e) => e.assignment === a.id).length;
    if (a.weekly_hours && done >= a.weekly_hours) {
      setError(`${a.subject} already has all ${a.weekly_hours} of its weekly periods.`);
      clearSelection();
      return;
    }
    setError("");
    saveEntry({ assignment: a.id, kind: "class", day, slotId });
  };

  const tryPlaceActivity = (day, slotId, ca) => {
    const key = `${day}_${slotId}`;
    if (freeCells && !freeCells.has(key)) {
      setError(`Can't place ${ca.name} there — this class already has something in that period.`);
      clearSelection();
      return;
    }
    if ((ca.placed || 0) >= ca.periods_per_week) {
      setError(`${ca.name} already has all ${ca.periods_per_week} of its weekly periods.`);
      clearSelection();
      return;
    }
    setError("");
    saveEntry({ class_activity: ca.id, kind: "activity", day, slotId });
  };

  const saveEntry = async ({ assignment, class_activity, kind, day, slotId }) => {
    try {
      await API.post("/timetable/", {
        kind,
        assignment: assignment || null,
        class_activity: class_activity || null,
        day_of_week: day,
        time_slot: slotId,
        room: kind === "activity" ? null : room || null,
      });
      await loadClass();
      await loadStatus();
      showToast("✓ Saved");
    } catch (err) {
      const data = err?.response?.data;
      const msg =
        (Array.isArray(data) ? data[0] : data?.detail) ||
        data?.non_field_errors?.[0] ||
        "Could not add — there may be a clash.";
      // A clash the server caught (teacher/room booked by another class) names
      // that class — show it in the center popup, not the thin bar.
      if (/already booked|is teaching|already has/i.test(String(msg))) {
        setPopup(msg);
      } else {
        setError(msg);
      }
    } finally {
      clearSelection();
    }
  };

  const remove = async (id) => {
    setError("");
    try {
      await API.delete(`/timetable/${id}/`);
      await loadClass();
      await loadStatus();
      showToast("✓ Removed");
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not remove — please try again.");
    }
  };

  const submitForApproval = async () => {
    setError("");
    setConflicts([]);
    try {
      await API.post("/timetable/submit/", { year: sel.year, semester: sel.semester });
      await loadStatus();
      showToast("✓ Submitted for approval");
    } catch (err) {
      const data = err?.response?.data;
      if (data?.conflicts?.length) {
        setConflicts(data.conflicts);
        await loadClass();
      } else {
        setError(data?.detail || "Could not submit.");
      }
    }
  };

  const moveEntry = async (entryId, day, slot) => {
    try {
      await API.post("/timetable/move/", { entry: entryId, day, slot });
      setConflicts((c) => c.filter((x) => x.entry !== entryId));
      await loadClass();
      showToast("✓ Moved");
    } catch (err) {
      // MEETING POINT 5: show why the move was refused (clash / locked)
      setError(err?.response?.data?.detail || "Could not move that class.");
    }
  };

  // ---------- AUTO-FILL CHOICE ----------
  // How many periods each subject / activity still needs.
  const subjectLeft = (a) =>
    Math.max(0, (a.weekly_hours || 0) - entries.filter((e) => e.assignment === a.id).length);
  const activityLeft = (c) =>
    Math.max(0, (c.periods_per_week || 0) - entries.filter((e) => e.class_activity === c.id).length);

  // Step 1: open the pop-up. Everything that still needs periods is ticked.
  const openAutoFill = () => {
    setError("");
    clearSelection();
    setAutoResult(null);
    setAutoPick({
      subjects: assignments.filter((a) => subjectLeft(a) > 0).map((a) => a.id),
      activities: classActs.filter((c) => activityLeft(c) > 0).map((c) => c.id),
    });
    setAutoOpen(true);
  };

  const togglePick = (kind, id) =>
    setAutoPick((p) => ({
      ...p,
      [kind]: p[kind].includes(id) ? p[kind].filter((x) => x !== id) : [...p[kind], id],
    }));

  const pickAll = (kind, on) =>
    setAutoPick((p) => ({
      ...p,
      [kind]: on
        ? (kind === "subjects"
            ? assignments.filter((a) => subjectLeft(a) > 0).map((a) => a.id)
            : classActs.filter((c) => activityLeft(c) > 0).map((c) => c.id))
        : [],
    }));

  // Redis/Celery work, step 6.5: auto-fill runs as a background job on the
  // server. Start it, then ask for its status every 2 seconds until it is done.
  const waitForJob = async (jobId) => {
    const started = Date.now();
    let hasStarted = false;                                // true once the worker picks it up
    while (Date.now() - started < 6 * 60 * 1000) {        // give up after 6 minutes
      const { data } = await API.get(`/jobs/${jobId}/`);
      if (data.status === "done") return data.result;
      if (data.status === "failed") throw new Error(data.error || "Auto-fill failed.");
      if (data.status !== "queued") hasStarted = true;
      // Still "queued" after 60 seconds: the worker is stopped or busy with another job.
      // Stop waiting, but the job stays in the queue and runs when the worker is free.
      if (!hasStarted && Date.now() - started > 60 * 1000) {
        throw new Error(
          "Auto-fill has not started yet. The background service may be stopped or busy. " +
          "It will run once the service is free. Check the timetable again later, " +
          "or ask the admin to check System health."
        );
      }
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    throw new Error(
      "Auto-fill is taking longer than expected. It may still be running in the background. " +
      "Please check the timetable again in a minute."
    );
  };

  // Step 2: run the solver with only the ticked items.
  const runAutoFill = async () => {
    setError("");
    setFilling(true);
    try {
      let jobId;
      try {
        const r = await API.post("/timetable/autofill/start/", {
          year: sel.year,
          semester: sel.semester,
          room: room || null,
          subjects: autoPick.subjects,
          activities: autoPick.activities,
        });
        jobId = r.data.job_id;
      } catch (err) {
        // already running for this class (another tab or another person):
        // follow that job instead of starting a second one
        if (err?.response?.status === 409 && err.response.data?.job_id) {
          jobId = err.response.data.job_id;
        } else {
          throw err;
        }
      }
      const result = await waitForJob(jobId);
      await loadClass();
      await loadStatus();
      setAutoResult({ message: result.message, not_placed: result.not_placed || [] });
    } catch (err) {
      setAutoOpen(false);
      // a "changed while running" failure may have left newer entries: show them
      await loadClass().catch(() => {});
      setError(err?.response?.data?.detail || err?.message || "Auto-fill could not run.");
    } finally {
      setFilling(false);
    }
  };

  const closeAutoFill = () => {
    if (filling) return;
    setAutoOpen(false);
    setAutoResult(null);
  };

  const noPeriods = slots.length === 0;
  const st = approval ? STATUS_STYLE[approval.status] || STATUS_STYLE.draft : null;
  const canSubmit =
    isHodMode && classReady && entries.length > 0 &&
    (!approval || approval.status === "draft" || approval.status === "rejected");

  const subjectHours = assignments.reduce((n, a) => n + (a.weekly_hours || 0), 0);
  const subjectPlaced = entries.filter((e) => e.kind !== "activity").length;
  const nothingToFill = assignments.length === 0 && classActs.length === 0;

  // AUTO-FILL CHOICE summary
  const teachSlots = slots.filter((s) => !s.is_break).length;
  const emptyCells = Math.max(0, teachSlots * DAYS.length - entries.length);
  const pickedPeriods =
    assignments.filter((a) => autoPick.subjects.includes(a.id)).reduce((n, a) => n + subjectLeft(a), 0) +
    classActs.filter((c) => autoPick.activities.includes(c.id)).reduce((n, c) => n + activityLeft(c), 0);

  return (
    <div style={{ position: "relative" }}>
      {toast && (
        <div
          style={{
            position: "fixed", top: 24, left: "50%", transform: "translateX(-50%)",
            zIndex: 1000, background: "#15803d", color: "#fff", fontSize: 15,
            fontWeight: 600, padding: "11px 22px", borderRadius: 12,
            boxShadow: "0 8px 24px rgba(0,0,0,.22)",
          }}
        >
          {toast}
        </div>
      )}

      {/* ---------- BUSY / CLASH POPUP (center modal) ---------- */}
      {popup && (
        <div
          onClick={() => setPopup("")}
          style={{
            position: "fixed", inset: 0, zIndex: 1100,
            background: "rgba(15,23,42,.45)",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: 20,
          }}
        >
          <div
            onClick={(ev) => ev.stopPropagation()}
            style={{
              background: "#fff", borderRadius: 16, maxWidth: 420, width: "100%",
              padding: "24px 24px 20px", textAlign: "center",
              boxShadow: "0 20px 60px rgba(0,0,0,.30)",
            }}
          >
            <div
              style={{
                width: 44, height: 44, borderRadius: "50%", margin: "0 auto 14px",
                background: "#fef2f2", color: "#dc2626",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 22, fontWeight: 800,
              }}
            >
              !
            </div>
            <h3 style={{ margin: "0 0 8px", fontSize: 17, color: "#17151F" }}>
              That period is taken
            </h3>
            <p style={{ margin: "0 0 20px", fontSize: 15.5, color: "#5D5A6B", lineHeight: 1.5 }}>
              {popup}
            </p>
            <button
              onClick={() => setPopup("")}
              style={{
                background: "#4B32C3", color: "#fff", border: "none", borderRadius: 10,
                padding: "10px 28px", fontSize: 15, fontWeight: 600, cursor: "pointer",
              }}
            >
              Got it
            </button>
          </div>
        </div>
      )}

            {/* ---------- AUTO-FILL CHOICE POP-UP (meeting point 1) ---------- */}
      {autoOpen && (
        <div
          onClick={closeAutoFill}
          style={{
            position: "fixed", inset: 0, zIndex: 1100,
            background: "rgba(15,23,42,.45)",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: 20,
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="autofill-title"
            onClick={(ev) => ev.stopPropagation()}
            style={{
              background: "#fff", borderRadius: 16, maxWidth: 520, width: "100%",
              maxHeight: "85vh", display: "flex", flexDirection: "column",
              boxShadow: "0 20px 60px rgba(0,0,0,.30)",
            }}
          >
            <div style={{ padding: "22px 24px 12px" }}>
              <h3 id="autofill-title" style={{ margin: "0 0 6px", fontSize: 17, color: "#17151F" }}>
                {autoResult ? "Auto-fill finished" : "✨ What should AI place?"}
              </h3>
              {!autoResult && (
                <p style={{ margin: 0, fontSize: 14.5, color: "#5D5A6B", lineHeight: 1.5 }}>
                  Tick the subjects and activities to place automatically. Cells you
                  already placed stay where they are. Unticked items are left for you
                  to place by hand.
                </p>
              )}
            </div>

            {autoResult ? (
              /* ---- STEP 2: result ---- */
              <div style={{ padding: "0 24px 8px", overflowY: "auto" }}>
                <p style={{ margin: "0 0 12px", fontSize: 15.5, color: "#15803d", fontWeight: 600 }}>
                  ✓ {autoResult.message}
                </p>
                {autoResult.not_placed.length > 0 && (
                  <div
                    style={{
                      background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 10,
                      padding: "10px 12px", fontSize: 14.5, color: "#8A4B0A",
                    }}
                  >
                    <div style={{ fontWeight: 700, marginBottom: 6 }}>Not placed — place these by hand:</div>
                    {autoResult.not_placed.map((n) => (
                      <div key={n.name}>
                        {n.name}: {n.short} {n.short === 1 ? "period" : "periods"}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              /* ---- STEP 1: choose ---- */
              <div style={{ padding: "0 24px 8px", overflowY: "auto" }}>
                {[
                  { kind: "subjects", title: "Subjects", items: assignments,
                    name: (a) => a.subject, who: (a) => a.teacher_name,
                    need: (a) => a.weekly_hours || 0, left: subjectLeft },
                  { kind: "activities", title: "Activities", items: classActs,
                    name: (c) => c.name, who: (c) => c.teacher_name || "No teacher",
                    need: (c) => c.periods_per_week || 0, left: activityLeft },
                ].map((g) =>
                  g.items.length === 0 ? null : (
                    <div key={g.kind} style={{ marginBottom: 14 }}>
                      <div
                        style={{
                          display: "flex", justifyContent: "space-between", alignItems: "center",
                          margin: "6px 0", fontSize: 14, fontWeight: 700, color: "#17151F",
                        }}
                      >
                        <span>{g.title}</span>
                        <span style={{ fontWeight: 500 }}>
                          <button type="button" className="tb-link" onClick={() => pickAll(g.kind, true)}>All</button>
                          {" · "}
                          <button type="button" className="tb-link" onClick={() => pickAll(g.kind, false)}>None</button>
                        </span>
                      </div>

                      {g.items.map((it) => {
                        const left = g.left(it);
                        const full = left === 0;
                        const on = autoPick[g.kind].includes(it.id);
                        return (
                          <label
                            key={it.id}
                            style={{
                              display: "flex", alignItems: "center", gap: 10,
                              padding: "8px 10px", marginBottom: 6, borderRadius: 10,
                              border: `1px solid ${on ? "#4B32C3" : "#E7E7EC"}`,
                              background: full ? "#F7F7F9" : on ? "#f5f2ff" : "#fff",
                              cursor: full ? "default" : "pointer",
                              opacity: full ? 0.6 : 1,
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={on}
                              disabled={full}
                              onChange={() => togglePick(g.kind, it.id)}
                            />
                            <span style={{ flex: 1, minWidth: 0 }}>
                              <span style={{ display: "block", fontSize: 15, fontWeight: 600, color: "#17151F" }}>
                                {g.name(it)}
                              </span>
                              <span style={{ fontSize: 13.5, color: "#5D5A6B" }}>
                                {g.who(it)} · {g.need(it) - left} of {g.need(it)} placed
                              </span>
                            </span>
                            <span
                              style={{
                                fontSize: 13.5, fontWeight: 700, whiteSpace: "nowrap",
                                color: full ? "#15803d" : "#4B32C3",
                              }}
                            >
                              {full ? "Full" : `${left} left`}
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  )
                )}

                <div
                  style={{
                    fontSize: 14.5, color: "#17151F", padding: "10px 12px", borderRadius: 10,
                    background: pickedPeriods > emptyCells ? "#fff7ed" : "#F7F7F9",
                    border: `1px solid ${pickedPeriods > emptyCells ? "#fed7aa" : "#E7E7EC"}`,
                  }}
                >
                  You picked <strong>{pickedPeriods}</strong> {pickedPeriods === 1 ? "period" : "periods"}.
                  The grid has <strong>{emptyCells}</strong> empty {emptyCells === 1 ? "cell" : "cells"}.
                  {pickedPeriods > emptyCells && (
                    <div style={{ color: "#8A4B0A", marginTop: 4 }}>
                      Not everything will fit. Some periods will stay unplaced.
                    </div>
                  )}
                </div>
              </div>
            )}

            <div
              style={{
                display: "flex", justifyContent: "flex-end", gap: 10,
                padding: "14px 24px 20px", borderTop: "1px solid #E7E7EC", marginTop: 8,
              }}
            >
              {autoResult ? (
                <button
                  type="button"
                  onClick={closeAutoFill}
                  style={{
                    background: "#4B32C3", color: "#fff", border: "none", borderRadius: 10,
                    padding: "10px 24px", fontSize: 15, fontWeight: 600, cursor: "pointer",
                  }}
                >
                  Done
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={closeAutoFill}
                    disabled={filling}
                    style={{
                      background: "#fff", color: "#5D5A6B", border: "1px solid #E7E7EC",
                      borderRadius: 10, padding: "10px 20px", fontSize: 15, fontWeight: 600,
                      cursor: filling ? "wait" : "pointer",
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={runAutoFill}
                    disabled={filling || pickedPeriods === 0}
                    style={{
                      background: "#4B32C3", color: "#fff", border: "none", borderRadius: 10,
                      padding: "10px 20px", fontSize: 15, fontWeight: 600,
                      cursor: filling ? "wait" : pickedPeriods === 0 ? "not-allowed" : "pointer",
                      opacity: pickedPeriods === 0 ? 0.5 : 1,
                    }}
                  >
                    {filling
                      ? "Placing…"
                      : `Auto-fill ${pickedPeriods} ${pickedPeriods === 1 ? "period" : "periods"}`}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ---------- class selectors ---------- */}
      <div className="tb-controls">
        <select value={sel.course} onChange={(e) => setSel({ ...sel, course: e.target.value })}>
          <option value="">Department / Course</option>
          {visibleCourses.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>

        <select
          value={sel.year}
          onChange={(e) => setSel({ ...sel, year: e.target.value, semester: "" })}
          disabled={!sel.course}
        >
          <option value="">Year</option>
          {years.map((y) => (
            <option key={y.id} value={y.id}>Year {y.year_number}</option>
          ))}
        </select>

        <select
          value={sel.semester}
          onChange={(e) => setSel({ ...sel, semester: e.target.value })}
          disabled={!sel.year}
        >
          <option value="">Semester</option>
          {legalSemesters.map((n) => (
            <option key={n} value={n}>Semester {n}</option>
          ))}
        </select>

        <select value={room} onChange={(e) => setRoom(e.target.value)} disabled={!classReady}>
          <option value="">Room (optional)</option>
          {rooms.map((r) => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>
      </div>

      {/* ---------- status bar (HOD only) ---------- */}
      {isHodMode && classReady && st && (
        <div
          style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            gap: 12, flexWrap: "wrap", margin: "14px 0", padding: "12px 14px",
            background: st.bg, border: `1px solid ${st.bd}`, borderRadius: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: st.fg }}>{st.label}</span>
            {approval.status === "rejected" && approval.remark && (
              <span style={{ fontSize: 13.5, color: "#dc2626" }}>— Admin: {approval.remark}</span>
            )}
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            {!locked && (
              <button
                onClick={openAutoFill}
                disabled={filling || nothingToFill}
                style={{
                  background: "#fff", color: "#4B32C3", border: "1px solid #4B32C3",
                  borderRadius: 8, padding: "8px 16px", fontSize: 14, fontWeight: 600,
                  cursor: filling ? "wait" : "pointer",
                  opacity: nothingToFill ? 0.5 : 1,
                }}
              >
                {filling ? "Thinking…" : "✨ Auto-fill with AI"}
              </button>
            )}

            {canSubmit && (
              <button
                onClick={submitForApproval}
                style={{
                  background: "#4B32C3", color: "#fff", border: "none", borderRadius: 8,
                  padding: "8px 16px", fontSize: 14, fontWeight: 600, cursor: "pointer",
                }}
              >
                Submit for approval
              </button>
            )}
          </div>
        </div>
      )}

      {error && <div className="tb-error">{error}</div>}

      {/* ---------- submit conflicts ---------- */}
      {conflicts.length > 0 && (
        <div className="tb-conflicts">
          <h4>
            {conflicts.length === 1
              ? "1 slot was taken while you were working"
              : `${conflicts.length} slots were taken while you were working`}
          </h4>
          <p>Fix just these cells, then submit again. The rest of your timetable is fine.</p>

          {conflicts.map((c) => (
            <div key={c.entry} className="tb-conflict">
              <div className="tb-conflict-what">
                <strong>{c.cell} — {c.subject}</strong>
                <span>{c.reason}</span>
              </div>
              <div className="tb-conflict-fix">
                {c.suggestions.length === 0 ? (
                  <span className="tb-conflict-none">No free slot for {c.teacher}</span>
                ) : (
                  c.suggestions.map((s) => (
                    <button
                      key={`${s.day}_${s.slot}`}
                      className="tb-btn tb-btn-sm"
                      onClick={() => moveEntry(c.entry, s.day, s.slot)}
                    >
                      Move to {s.label}
                    </button>
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {noPeriods ? (
        <div className="tb-empty">
          No periods set up yet.{" "}
          {goToPeriods ? (
            <button className="tb-link" onClick={goToPeriods}>Set up periods first →</button>
          ) : (
            <span>Ask the admin to set up the daily periods first.</span>
          )}
        </div>
      ) : !classReady ? (
        <div className="tb-empty">Select a department, year and semester to begin.</div>
      ) : loading ? (
        <div className="tb-empty">Loading…</div>
      ) : (
        <>
          {locked && (
            <div style={{ fontSize: 13.5, color: "#8A4B0A", marginBottom: 10 }}>
              This timetable is submitted and locked. The admin must approve or reject it
              before you can edit again.
            </div>
          )}

          <div className={`tb-hint ${hint ? "" : "tb-hint-empty"}`}>
            {hint ||
              (locked
                ? ""
                : "Click a subject or activity, then click a slot. Grey means that teacher is busy.")}
          </div>

          <div className="tb-layout">
            {/* ================= PALETTE ================= */}
            {!locked && (
              <div className="tb-palette">

                {/* ---- ACTIVITY CONFIG: set once, Auto-fill remembers ---- */}
                <div className="tb-acts">
                  <button className="tb-acts-head" onClick={() => setShowActs(!showActs)}>
                    <span>Activities ({classActs.length})</span>
                    <span>{showActs ? "▾" : "▸"}</span>
                  </button>

                  {showActs && (
                    <div className="tb-acts-body">
                      {activityTypes.map((t) => {
                        const mine = classActs.find((c) => c.activity === t.id);
                        return (
                          <div key={t.id} className="tb-act-row">
                            <label>
                              <input
                                type="checkbox"
                                checked={!!mine}
                                onChange={(e) => toggleActivity(t, e.target.checked)}
                              />
                              <i className="tb-act-dot" style={{ background: t.colour }} />
                              {t.name}
                            </label>
                            {mine && (
                              <input
                                type="number"
                                min="1"
                                max="6"
                                className="tb-act-n"
                                value={mine.periods_per_week}
                                onChange={(e) => setActivityHours(mine, e.target.value)}
                              />
                            )}
                          </div>
                        );
                      })}

                      <div className="tb-act-add">
                        <input
                          placeholder="Add your own…"
                          value={newAct}
                          onChange={(e) => setNewAct(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && addOwnActivity()}
                        />
                        <button className="tb-btn tb-btn-sm" onClick={addOwnActivity}>
                          Add
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* ---- ACTIVITY CHIPS ---- */}
                {classActs.map((c) => {
                  const done = c.placed || 0;
                  const full = done >= c.periods_per_week;
                  const on = selected?.type === "activity" && selected.data.id === c.id;
                  return (
                    <div
                      key={`act${c.id}`}
                      className={
                        "tb-chip tb-chip-act" +
                        (full ? " tb-chip-full" : "") +
                        (on ? " tb-chip-on" : "")
                      }
                      style={{ borderLeft: `4px solid ${c.colour}` }}
                      draggable
                      onDragStart={() => {
                        setSelected({ type: "activity", data: c });
                        setDragging(null);
                        paintForActivity(c);
                      }}
                      onClick={() => toggleSelectActivity(c)}
                    >
                      <div className="tb-chip-name">{c.name}</div>
                      <div className="tb-chip-meta">
                        {c.teacher_name || "No teacher"} · {done} of {c.periods_per_week} placed
                      </div>
                      <div className="tb-chip-bar">
                        <div
                          className="tb-chip-fill"
                          style={{
                            width: `${Math.min((done / c.periods_per_week) * 100, 100)}%`,
                            background: c.colour,
                          }}
                        />
                      </div>
                    </div>
                  );
                })}

                {/* ---- SUBJECT CHIPS ---- */}
                <div className="tb-palette-head" style={{ marginTop: classActs.length ? 16 : 0 }}>
                  Subjects · {subjectPlaced} of {subjectHours} hours placed
                </div>

                {assignments.length === 0 && (
                  <p className="tb-state">
                    No subjects assigned to this class yet. Ask the admin to add them in
                    Faculty Allocation.
                  </p>
                )}

                {assignments.map((a) => {
                  const need = a.weekly_hours || 0;
                  const done = entries.filter((e) => e.assignment === a.id).length;
                  const full = need > 0 && done >= need;
                  const on = selected?.type === "subject" && selected.data.id === a.id;

                  return (
                    <div
                      key={a.id}
                      className={
                        "tb-chip" +
                        (full ? " tb-chip-full" : "") +
                        (dragging?.id === a.id ? " tb-chip-drag" : "") +
                        (on ? " tb-chip-on" : "")
                      }
                      draggable
                      onClick={() => toggleSelectSubject(a)}
                      onDragStart={() => onDragStart(a)}
                      onDragEnd={onDragEnd}
                    >
                      <div className="tb-chip-name">{a.subject}</div>
                      <div className="tb-chip-meta">
                        {a.teacher_name} · {done} of {need} placed
                      </div>
                      <div className="tb-chip-bar">
                        <div
                          className={full ? "tb-chip-fill tb-chip-fill-full" : "tb-chip-fill"}
                          style={{ width: need ? `${Math.min((done / need) * 100, 100)}%` : "0%" }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* ================= GRID ================= */}
            <div className="tb-wrap">
              <table className="tb-grid">
                <thead>
                  <tr>
                    <th className="tb-corner">Period</th>
                    {DAYS.map((d) => <th key={d.value}>{d.label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {slots.map((slot) =>
                    slot.is_break ? (
                      <tr key={slot.id} className="tb-brkrow">
                        <td className="tb-per">
                          {slot.label || "Break"}
                          <span>{fmt(slot.start_time)}–{fmt(slot.end_time)}</span>
                        </td>
                        <td colSpan={DAYS.length}>{slot.label || "Break"}</td>
                      </tr>
                    ) : (
                      <tr key={slot.id}>
                        <td className="tb-per">
                          P{slot.period_no}
                          <span>{fmt(slot.start_time)}–{fmt(slot.end_time)}</span>
                        </td>

                        {DAYS.map((d) => {
                          const key = `${d.value}_${slot.id}`;
                          const e = lookup[key];
                          const isAct = e?.kind === "activity";

                          const isGrey = painting && !e && !freeCells?.has(key);
                          const isGreen = painting && !e && freeCells?.has(key);
                          const reason = blockedCells?.get(key) || "";
                          const whoBusy = busy[key];

                          let cls = "tb-cell";
                          if (e) cls += isAct ? " tb-cell-act" : " tb-cell-has";
                          else if (isGrey) cls += " tb-cell-no";
                          else if (isGreen) cls += " tb-cell-ok";

                          const style = isAct && e.activity_colour
                            ? {
                                background: `${e.activity_colour}22`,
                                borderColor: e.activity_colour,
                                color: e.activity_colour,
                              }
                            : undefined;

                          return (
                            <td key={d.value}>
                              <div
                                className={cls}
                                style={style}
                                title={reason || (whoBusy ? `${whoBusy.join(", ")} busy elsewhere` : "")}
                                onDragOver={(ev) => ev.preventDefault()}
                                onDrop={(ev) => {
                                  ev.preventDefault();
                                  if (locked || e) return;
                                  const dropKey = `${d.value}_${slot.id}`;
                                  if (freeCells && !freeCells.has(dropKey)) {
                                    // dropped on a blocked cell — say why
                                    if (dragging) {
                                      tryPlaceSubject(d.value, slot.id, dragging);
                                    } else if (selected?.type === "activity") {
                                      tryPlaceActivity(d.value, slot.id, selected.data);
                                    }
                                    return;
                                  }
                                  if (dragging) {
                                    tryPlaceSubject(d.value, slot.id, dragging);
                                  } else if (selected?.type === "activity") {
                                    tryPlaceActivity(d.value, slot.id, selected.data);
                                  }
                                }}
                                onDragEnd={() => { if (!selected) clearSelection(); }}
                                onClick={() => {
                                  if (locked) return;
                                  if (e) { remove(e.id); return; }
                                  if (!selected) {
                                    setTyping(key);
                                    setTypeText("");
                                    return;
                                  }
                                  if (selected.type === "subject")
                                    tryPlaceSubject(d.value, slot.id, selected.data);
                                  else
                                    tryPlaceActivity(d.value, slot.id, selected.data);
                                }}
                              >
                                {typing === key ? (
                                  <input
                                    className="tb-type"
                                    autoFocus
                                    placeholder="Type a name…"
                                    value={typeText}
                                    onClick={(ev) => ev.stopPropagation()}
                                    onChange={(ev) => setTypeText(ev.target.value)}
                                    onKeyDown={(ev) => {
                                      if (ev.key === "Enter")
                                        placeTypedActivity(d.value, slot.id, typeText);
                                      if (ev.key === "Escape") {
                                        setTyping(null);
                                        setTypeText("");
                                      }
                                    }}
                                    onBlur={() => { setTyping(null); setTypeText(""); }}
                                  />
                                ) : e ? (
                                  <>
                                    {!locked && (
                                      <button
                                        className="tb-x"
                                        title="Remove"
                                        onClick={(ev) => { ev.stopPropagation(); remove(e.id); }}
                                      >
                                        ×
                                      </button>
                                    )}
                                    <strong>{e.subject}</strong>
                                    <small>
                                      {isAct
                                        ? (e.teacher_name || "activity")
                                        : (e.room_name || e.teacher_name)}
                                    </small>
                                  </>
                                ) : locked ? (
                                  <span className="tb-free">—</span>
                                ) : isGrey ? (
                                  <span className="tb-plus" />
                                ) : whoBusy && !painting ? (
                                  <small className="tb-busy">{whoBusy.join(", ")} busy</small>
                                ) : (
                                  <span className="tb-plus">+</span>
                                )}
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}