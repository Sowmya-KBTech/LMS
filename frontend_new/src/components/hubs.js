export const TONES = ["aca", "exm", "men", "com", "dep", "plc", "brand"];

const L = (label, path, icon, extra = {}) => ({ label, path, icon, ...extra });
const G = (id, title, links) => ({ id, title, links: links.filter(Boolean) });

// shown when the current page is not in any of the role's groups
export const ACCOUNT_HUB = G("account", "Account", [
  L("Profile", "/profile", "user"),
  L("Change password", "/change-password", "lock"),
  L("Notifications", "/notifications", "bell"),
]);

// ---------------- which backend module each page needs ----------------
// [path prefix, module]. A prefix matches the page itself and everything
// under it (/placement matches /placement/drives). Entries with ?tab=…
// match only that section. Module names = keys in backend
// config/module_registry.py.
export const PAGE_MODULES = [
  // learning
  ["/teacher-progress", "learning"],
  ["/student-progress", "learning"],
  ["/student/grades", "learning"],
  ["/parent/grades", "learning"],
  ["/parent/assignments", "learning"],
  ["/assignments", "learning"],
  ["/feedback", "learning"],
  // fees
  ["/admin/fees", "fees"],
  ["/parent/fees", "fees"],
  // messaging
  ["/teacher/messages", "messaging"],
  ["/parent/chat", "messaging"],
  ["/parent/messages", "messaging"],
  // timetable
  ["/timetable-builder", "timetable"],
  ["/timetable", "timetable"],
  ["/planner", "timetable"],                       // WAVE 1: student planner
  ["/parent/planner", "timetable"],
  ["/my-department?tab=timetable", "timetable"],
  // attendance (includes OD and staff leave)
  ["/teacher/attendance", "attendance"],
  ["/student/attendance", "attendance"],
  ["/parent/attendance", "attendance"],
  ["/teacher/leave", "attendance"],
  ["/my-department?tab=staffleave", "attendance"],
  ["/my-department?tab=requests", "attendance"],   // student on duty + leave
  // exams
  ["/results", "exams"],
  ["/my-department?tab=results", "exams"],
  ["/rank-list", "exams"],                         // WAVE 1: rank lists
  ["/my-progress-report", "exams"],                // WAVE 1: progress reports
  ["/parent/progress-report", "exams"],
  ["/my-credits", "exams"],                        // WAVE 3 PART 1B (CBCS)
  ["/exam-sessions", "exams"],                     // WAVE 3 PART 2
  ["/exam-registration", "exams"],
  ["/parent/credits", "exams"],
  ["/credits/", "exams"],
  // events
  ["/announcements", "events"],
  ["/calendar", "events"],
  // teaching plan
  ["/teacher/teaching-plan", "teachingplan"],
  ["/student/teaching-plan", "teachingplan"],
  ["/my-department/teaching-plans", "teachingplan"],
  // placement
  ["/placement", "placement"],
  ["/student/placement", "placement"],
  // mentoring
  ["/my-mentees", "mentoring"],
  ["/my-mentor", "mentoring"],
  ["/hod/mentor-allocation", "mentoring"],
  ["/hod/mentor-dashboard", "mentoring"],
  ["/hod/mentor-change-requests", "mentoring"],
  ["/hod/mentor-history", "mentoring"],
  ["/hod/mentor-settings", "mentoring"],
  ["/hod/mentors", "mentoring"],
  ["/hod/team-proposals", "mentoring"],
  // class groups
  ["/my-groups", "classgroups"],
  // surveys (WAVE 2)
  ["/surveys", "surveys"],
  // NAAC / NBA reports (WAVE 2)
  ["/accreditation", "accreditation"],
  ["/outcomes", "teachingplan"],                                  // CO-PO PART A
];

// → module name the page needs, or null for core pages.
// pathOrLink may carry ?tab=…; `search` is the current location.search.
export function moduleForPath(pathOrLink, search = "") {
  const [pathname, query = ""] = pathOrLink.split("?");
  const have = new URLSearchParams(query || search);
  let best = null;
  let bestLen = -1;
  PAGE_MODULES.forEach(([entry, mod]) => {
    const [ePath, eQuery] = entry.split("?");
    if (eQuery) {
      if (pathname !== ePath) return;
      const want = new URLSearchParams(eQuery);
      for (const [k, v] of want) if (have.get(k) !== v) return;
      if (entry.length > bestLen) { best = mod; bestLen = entry.length; }
      return;
    }
    if ((pathname === ePath || pathname.startsWith(`${ePath}/`)) && ePath.length > bestLen) {
      best = mod;
      bestLen = ePath.length;
    }
  });
  return best;
}

// modules = result of useModules(). Unknown / still loading → show all.
const moduleOn = (modules, mod) =>
  !mod || !modules?.loaded || modules.enabled.includes(mod);

function applyModules(hubs, modules) {
  if (!modules?.loaded) return hubs;
  const keep = (l) => moduleOn(modules, moduleForPath(l.path));
  return hubs
    .map((hub) => ({
      ...hub,
      links: hub.links
        .filter(keep)
        .map((l) => (l.children ? { ...l, children: l.children.filter(keep) } : l)),
    }))
    .filter((hub) => hub.links.length > 0);
}

// ---------------- user helpers ----------------
export const readUser = () => {
  try {
    return JSON.parse(localStorage.getItem("user") || "{}") || {};
  } catch {
    return {};
  }
};

export const isMainAdmin = (user) =>
  user?.is_superuser === true || (user?.role === "admin" && !user?.sub_role);

const SUB_ROLE_LABEL = {
  accounts_admin: "Accounts",
  exam_admin: "Examination",
  academic_admin: "Academic admin",
  iqac_admin: "IQAC",
  placement_officer: "Placement officer",
};

export function roleLabel(user, flags = {}) {
  if (!user?.role && !user?.is_superuser) return "";
  if (isMainAdmin(user)) return "Super admin";
  if (user.role === "admin") return SUB_ROLE_LABEL[user.sub_role] || "Admin";
  if (user.role === "teacher") {
    if (flags.isPrincipal) return "Principal";                 // WAVE 2
    return flags.isHod ? "Faculty · HOD" : "Faculty";
  }
  if (user.role === "student") return "Student";
  if (user.role === "parent") return "Parent";
  return user.role;
}

export const initialsOf = (name = "") => {
  const parts = String(name).trim().split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
};

// Where the "home" button goes. Must agree with RoleRedirect in App.jsx —
// sub-admins have no hub home page, so home is their landing page.
export function homePath(user) {
  if (!user) return "/";
  if (user.is_superuser === true) return "/dashboard";
  if (user.role === "admin") {
    const map = {
      accounts_admin: "/admin/fees",
      exam_admin: "/results",
      academic_admin: "/courses",
      iqac_admin: "/iqac",
      placement_officer: "/placement",
    };
    return map[user.sub_role] || "/dashboard";
  }
  if (user.role === "teacher") return "/teacher";
  if (user.role === "student") return "/student";
  if (user.role === "parent") return "/parent";
  return "/";
}

// ---------------- the groups, per role ----------------
const placementOfficeLinks = () => [
  L("Overview", "/placement", "grid"),
  L("Coordinators", "/placement/coordinators", "userCheck"),
  L("Companies", "/placement/companies", "building"),
  L("Drives", "/placement/drives", "calendar"),
  L("Applications", "/placement/applications", "clipboard"),
  L("Rounds & attendance", "/placement/rounds", "chat", { match: ["/placement/interviews"] }),
  L("Offers", "/placement/offers", "award"),
  L("Reports", "/placement/reports", "chart"),
];

const profileLink = () => L("Profile", "/profile", "user", { match: ["/change-password"] });

// modules = result of useModules(); null/loading → nothing is hidden
export function buildHubs(user, flags = {}, modules = null) {
  return applyModules(buildAllHubs(user, flags), modules);
}

function buildAllHubs(user, flags = {}) {
  if (!user || (!user.role && !user.is_superuser)) return [];

  // ================= SUPER ADMIN =================
  if (isMainAdmin(user)) {
    return [
      G("overview", "Overview", [
        L("Dashboard", "/dashboard", "grid"),
        L("Announcements", "/announcements", "megaphone"),
        L("Calendar", "/calendar", "calendar"),
      ]),
      G("academics", "Academics", [
        L("Departments", "/departments", "building"),
        L("Courses", "/courses", "layers"),
        L("Regulations", "/regulations", "book"),                     // WAVE 3 (CBCS)
        L("Credits and categories", "/curriculum", "layers"),         // WAVE 3 (CBCS)
        L("Electives", "/electives/manage", "check"),
        L("Outcomes (CO–PO)", "/outcomes", "chart"),                  // CO-PO PART A
        L("Timetable Builder", "/timetable-builder", "table"),
        L("Results", "/results", "exam"),
        L("Exam sessions", "/exam-sessions", "calendar"),             // WAVE 3 PART 2
        L("Rank lists", "/rank-list", "chart"),                       // WAVE 1
        L("Accreditation reports", "/accreditation", "shield"),       // WAVE 2
      ]),
      G("administration", "Administration", [
        L("User Management", "/users", "people"),
        L("Staff records", "/staff", "people"),                       // HRIS PART A
        L("Principal", "/principal", "award"),                        // WAVE 2
        L("Surveys", "/surveys/manage", "clipboard"),                 // WAVE 2
        L("Fee Management", "/admin/fees", "rupee"),
        L("Placement", "/placement", "briefcase", { children: placementOfficeLinks().slice(1) }),
        // Point 12, step 8: nightly reminder jobs
        L("Automation", "/admin/automation", "settings"),
      ]),
      G("account", "Account", [profileLink()]),
    ];
  }

  // ================= SUB-ADMINS =================
  if (user.role === "admin") {
    const account = G("account", "Account", [profileLink(), L("Notifications", "/notifications", "bell")]);
    switch (user.sub_role) {
      case "accounts_admin":
        return [
          G("fees", "Fees", [L("Fee Management", "/admin/fees", "rupee")]),
          G("campus", "Campus", [L("Announcements", "/announcements", "megaphone")]),
          account,
        ];
      case "exam_admin":
        return [
          G("exams", "Examinations", [
            L("Results", "/results", "exam"),
            L("Exam sessions", "/exam-sessions", "calendar"),         // WAVE 3 PART 2
            L("Rank lists", "/rank-list", "chart"),
            L("Regulations", "/regulations", "book"),                 // WAVE 3 (CBCS)
            L("Credits and categories", "/curriculum", "layers"),     // WAVE 3 (CBCS)
          ]),
          G("campus", "Campus", [L("Announcements", "/announcements", "megaphone")]),
          account,
        ];
      case "academic_admin":
        return [
          G("academics", "Academics", [
            L("Departments", "/departments", "building"),
            L("Courses", "/courses", "layers"),
            L("Regulations", "/regulations", "book"),                 // WAVE 3 (CBCS)
            L("Credits and categories", "/curriculum", "layers"),     // WAVE 3 (CBCS)
            L("Electives", "/electives/manage", "check"),
            L("Outcomes (CO–PO)", "/outcomes", "chart"),              // CO-PO PART A
            L("Surveys", "/surveys/manage", "clipboard"),             // WAVE 2
          ]),
          account,
        ];
      case "iqac_admin":
        return [
          G("iqac", "Quality (IQAC)", [
            L("Faculty participation", "/iqac", "people"),
            L("Academic quality", "/iqac/academic-quality", "chart"),
            L("Outcomes (CO–PO)", "/outcomes", "chart"),              // CO-PO PART A
            L("Surveys", "/surveys/manage", "clipboard"),             // WAVE 2
            L("Accreditation reports", "/accreditation", "shield"),   // WAVE 2
          ]),
          account,
        ];
      case "placement_officer":
        return [
          G("placement", "Placement", placementOfficeLinks()),
          G("campus", "Campus", [L("Announcements", "/announcements", "megaphone")]),
          account,
        ];
      default:
        return [account];
    }
  }

  // ================= FACULTY =================
  if (user.role === "teacher") {
    return [
      G("overview", "Overview", [
        L("Dashboard", "/teacher", "grid"),
        L("Notifications", "/notifications", "bell"),
      ]),
      // WAVE 2: the Principal's college-wide pages
      flags.isPrincipal &&
        G("principal", "Principal", [
          L("College overview", "/principal", "building"),
          L("Staff records", "/staff", "people"),                      // HRIS PART A
          L("Rank lists", "/rank-list", "chart", { match: ["/progress-report/"] }),
          L("Surveys", "/surveys/manage", "clipboard"),                // WAVE 2
          L("Accreditation reports", "/accreditation", "shield"),      // WAVE 2
          L("Outcomes (CO–PO)", "/outcomes", "chart"),                 // CO-PO PART A
        ]),
      G("teaching", "Teaching", [
        L("My Subjects", "/teacher/courses", "book", { match: ["/teacher/subject/", "/assignments/"] }),
        L("Timetable", "/timetable", "table"),
        L("My Teaching Plan", "/teacher/teaching-plan", "clipboard"),
        L("Attendance", "/teacher/attendance", "userCheck"),
        L("Results", "/results", "exam"),
        !flags.isPrincipal && (flags.isHod || flags.isTutor) && L("Rank lists", "/rank-list", "chart", { match: ["/progress-report/"] }),   // WAVE 1
        L("Student Progress", "/teacher-progress", "chart"),
      ]),
      flags.isHod &&
        G("hod", "Head of Department", [
          // sections of HODDepartment.jsx — ?tab keys must match its SECTIONS
          L("My Department", "/my-department", "building", {
            children: [
              L("Results", "/my-department?tab=results"),
              L("Timetable", "/my-department?tab=timetable"),
              L("Students", "/my-department?tab=students"),
              L("Class in-charges", "/my-department?tab=tutors"),
              L("Student requests", "/my-department?tab=requests"),   // on duty + leave
              L("Staff leave", "/my-department?tab=staffleave"),
            ],
          }),
          L("Plan Approvals", "/my-department/teaching-plans", "check"),
          L("Faculty Allocation", "/hod/allocation", "people"),
          !flags.isPrincipal && L("Staff records", "/staff", "people"),   // HRIS PART A
          L("Electives", "/electives/manage", "check"),
          !flags.isPrincipal && L("Outcomes (CO–PO)", "/outcomes", "chart"),   // CO-PO PART A
          !flags.isPrincipal && L("Surveys", "/surveys/manage", "clipboard"),   // WAVE 2 (Principal has it above)
          !flags.isPrincipal && L("Accreditation reports", "/accreditation", "shield"),
          L("Mentor Allocation", "/hod/mentor-allocation", "group", {
            match: ["/hod/mentor", "/hod/mentors/", "/hod/team-proposals"],
          }),
        ]),
      G("people", "People", [
        // sections of StaffMyMentees.jsx — ?tab keys must match its SECTIONS
        L("My Mentees", "/my-mentees", "group", {
          children: [
            L("Change requests", "/my-mentees?tab=requests"),
            L("Messages", "/my-mentees?tab=messages"),
            L("Group message", "/my-mentees?tab=groups"),
            ...(flags.isTutor
              ? [L("Team formation", "/my-mentees?tab=teams"), L("Pick mentors", "/my-mentees?tab=mentors")]
              : []),
          ],
        }),
        flags.isTutor && L("My Class", "/my-class", "cap"),
        L("My Groups", "/my-groups", "people"),
        L("Parent Messages", "/teacher/messages", "chat"),
      ]),
      G("campus", "Campus", [
        L("Calendar", "/calendar", "calendar"),
        L("Announcements", "/announcements", "megaphone"),
        L("Feedback History", "/feedback", "star"),
        L("My surveys", "/surveys", "clipboard"),                         // WAVE 2: answering
        L("My Contributions", "/my-contributions", "award"),
        // only a teacher who ALSO holds a coordinator assignment
        flags.isPlacementCoordinator && L("Placement Coordination", "/placement/coordinator", "briefcase"),
      ]),
      G("me", "Me", [
        L("My Leave", "/teacher/leave", "clock"),
        !flags.isHod && !flags.isPrincipal && L("My staff record", "/staff", "clipboard"),   // HRIS PART A
        L("My appraisal", "/staff?tab=appraisal", "award"),                 // HRIS PART B
        profileLink(),
      ]),
    ].filter(Boolean);
  }

  // ================= STUDENT =================
  if (user.role === "student") {
    return [
      G("overview", "Overview", [
        L("Dashboard", "/student", "grid"),
        L("My Planner", "/planner", "calendar"),                      // WAVE 1
        L("Notifications", "/notifications", "bell"),
      ]),
      G("academics", "Academics", [
        L("My Subjects", "/student/courses", "book", {
          match: ["/student/subject/", "/student/teaching-plan", "/assignments/"],
        }),
        L("Electives", "/student/electives", "layers"),
        L("Timetable", "/timetable", "table"),
        L("Attendance", "/student/attendance", "userCheck", {
          children: [
            L("On duty requests", "/student/attendance?tab=onduty"),
            L("Leave requests", "/student/attendance?tab=leave"),     // WAVE 1
          ],
        }),
        L("Grades", "/student/grades", "star"),
        L("Results", "/results", "exam"),
        L("Progress report", "/my-progress-report", "clipboard"),     // WAVE 1
        L("My credits", "/my-credits", "award"),                      // WAVE 3 (CBCS)
        L("Exam registration", "/exam-registration", "clipboard"),    // WAVE 3 PART 2
        L("My Progress", "/student-progress", "chart"),
      ]),
      G("campus", "Campus", [
        L("My Mentor", "/my-mentor", "userCheck"),
        L("My Groups", "/my-groups", "people"),
        L("Placement", "/student/placement", "briefcase"),
        L("Calendar", "/calendar", "calendar"),
        L("Announcements", "/announcements", "megaphone"),
        L("Feedback History", "/feedback", "chat"),
        L("Surveys", "/surveys", "clipboard"),                          // WAVE 2
      ]),
      G("account", "Account", [profileLink()]),
    ];
  }

  // ================= PARENT =================
  if (user.role === "parent") {
    return [
      G("overview", "Overview", [
        L("Dashboard", "/parent", "grid"),
        L("Planner", "/parent/planner", "calendar"),                  // WAVE 1
        L("Notifications", "/notifications", "bell"),
      ]),
      G("child", "My Child", [
        L("Attendance", "/parent/attendance", "userCheck"),
        L("Assignments", "/parent/assignments", "clipboard"),
        L("Grades", "/parent/grades", "star"),
        L("Results", "/results", "exam"),
        L("Progress report", "/parent/progress-report", "clipboard"), // WAVE 1
        L("Credits and CGPA", "/parent/credits", "award"),            // WAVE 3 (CBCS)
      ]),
      G("payments", "Payments", [L("Fees", "/parent/fees", "rupee")]),
      G("talk", "Talk to teachers", [
        L("Messages", "/parent/chat", "chat", { match: ["/parent/messages"] }),
      ]),
      G("account", "Account", [profileLink()]),
    ];
  }

  return [];
}

// ---------------- path matching ----------------
// How strongly a link "owns" the current path. Exact match always wins;
// otherwise the longest matching prefix wins, so /placement/drives/4
// belongs to "Drives", not to "Placement" (/placement).
function score(link, pathname, search = "") {
  const [path, query] = link.path.split("?");

  // links that carry ?tab=… own only that exact section
  if (query) {
    if (pathname !== path) return -1;
    const want = new URLSearchParams(query);
    const have = new URLSearchParams(search);
    for (const [k, v] of want) if (have.get(k) !== v) return -1;
    return 100001; // beats the plain link to the same page
  }

  if (pathname === path) return 100000;
  const prefixes = [`${path}/`, ...(link.match || [])];
  let best = -1;
  prefixes.forEach((p) => {
    if (pathname.startsWith(p) && p.length > best) best = p.length;
  });
  return best;
}

// → { hub, link, parent } for the current path. `link` is the best match
//   (may be a child); `parent` is the top-level link it sits under.
export function locate(hubs, pathname, search = "") {
  let best = { hub: null, link: null, parent: null, s: -1 };

  hubs.forEach((hub) =>
    hub.links.forEach((link) => {
      const s = score(link, pathname, search);
      if (s > best.s) best = { hub, link, parent: link, s };
      (link.children || []).forEach((child) => {
        const cs = score(child, pathname, search);
        if (cs > best.s) best = { hub, link: child, parent: link, s: cs };
      });
    })
  );

  if (best.s >= 0) return best;

  const acc = ACCOUNT_HUB.links.find((l) => score(l, pathname, search) >= 0);
  if (acc) return { hub: ACCOUNT_HUB, link: acc, parent: acc, s: 0 };

  return { hub: null, link: null, parent: null, s: -1 };
}

// flat list for the search box (children are searchable too)
export function searchIndex(hubs) {
  const seen = new Set();
  const out = [];
  [...hubs, ACCOUNT_HUB].forEach((hub) =>
    hub.links.forEach((link) => {
      [link, ...(link.children || [])].forEach((l) => {
        if (seen.has(l.path)) return;
        seen.add(l.path);
        out.push({
          ...l,
          hubTitle: l === link ? hub.title : link.label,
          tone: "brand",
        });
      });
    })
  );
  return out;
}

// ---------------- greeting helpers (home pages) ----------------
export const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
};

export const todayLine = () =>
  new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" });