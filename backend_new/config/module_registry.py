# backend/config/module_registry.py
"""
Module registry for KB Tech Campus.

This file is the ONE place that knows:
  - which modules exist
  - which are core (always on) and which are optional
  - which other modules each one needs ("requires")
  - which URL files each one loads

Each college picks its modules with one line in backend/.env:

    ENABLED_MODULES=all
    ENABLED_MODULES=learning,fees,attendance,timetable,exams
    ENABLED_MODULES=none          (core only)

If the line is missing or says "all", every module is turned on.

RULES FOR DEVELOPERS
  1. Core never imports an optional module at the top of a file.
  2. A module may import another module freely ONLY if it lists it in
     "requires" below.
  3. Any other link must be optional - use module_enabled(), optional_model()
     or optional_function() from this file, so the code still works when
     that module is switched off.
"""

import importlib

from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist


# Order matters: apps are installed and URLs are loaded in this order.
# "early_urls" are loaded BEFORE every normal URL file. They are used for
# module URLs that live under /api/users/ (users.urls ends with a catch-all
# <pk>/ route, so anything after it would never be reached).
MODULES = {
    # ======================= CORE (always on) =======================
    "users": {
        "label": "Users, Roles & Departments",
        "path": "core.users",
        "core": True,
        "requires": [],
        "urls": [("api/users/", "core.users.urls")],
    },
    "courses": {
        # Folder: core/academics. App label stays "courses" so the existing
        # database tables (courses_course, courses_subject, ...) and migration
        # history do not change.
        "label": "Academics (courses, subjects, enrollments)",
        "path": "core.academics",
        "core": True,
        "requires": [],
        "urls": [("api/", "core.academics.urls")],
    },
    "notifications": {
        "label": "Notifications & Emails",
        "path": "core.notifications",
        "core": True,
        "requires": [],
        "urls": [("api/", "core.notifications.urls")],
    },
    "dataio": {
        # One shared import/export engine. Importers plug in from their own
        # app (core.dataio.importers.* for core, modules register their own),
        # so a switched-off module has no import/export either.
        "label": "Import & Export",
        "path": "core.dataio",
        "core": True,
        "requires": [],
        "urls": [("api/dataio/", "core.dataio.urls")],
    },
    # AUTOMATION (Point 12, step 4): the nightly job runner. Core (always on),
    # like notifications; each job checks that its own module is switched on.
    "automation": {
        "label": "Automation (background jobs)",
        "path": "modules.automation",
        "core": True,
        "requires": [],
        "urls": [("api/", "modules.automation.urls")],   # step 8: Admin -> Automation
    },

    # ======================= OPTIONAL MODULES =======================
    "learning": {
        "label": "Learning (lectures, assignments, quizzes, materials)",
        "path": "modules.learning",
        "core": False,
        "requires": [],
        "urls": [("api/", "modules.learning.urls")],
    },
    "fees": {
        "label": "Fees & Online Payments",
        "path": "modules.fees",
        "core": False,
        "requires": [],
        "urls": [("api/", "modules.fees.urls")],
    },
    "messaging": {
        "label": "Messaging (parent messages & chat)",
        "path": "modules.messaging",
        "core": False,
        "requires": [],
        "urls": [("api/", "modules.messaging.urls")],
    },
    "timetable": {
        "label": "Timetable",
        "path": "modules.timetable",
        "core": False,
        "requires": [],
        "urls": [("api/", "modules.timetable.urls")],
    },
    "attendance": {
        "label": "Attendance, OD & Staff Leave",
        "path": "modules.attendance",
        "core": False,
        "requires": [],
        "early_urls": [("api/users/", "modules.attendance.users_urls")],
        "urls": [("api/", "modules.attendance.urls")],
    },
    "exams": {
        "label": "Examinations & Results",
        "path": "modules.exams",
        "core": False,
        # Exam fees, attendance fines and revaluation fees are Fee rows
        # (RevaluationRequest has a database link to Fee).
        "requires": ["fees"],
        "early_urls": [("api/users/", "modules.exams.users_urls")],
        "urls": [("api/", "modules.exams.urls")],
    },
    "events": {
        "label": "Events, Calendar & Announcements",
        "path": "modules.events",
        "core": False,
        "requires": [],
        "urls": [("api/", "modules.events.urls")],
    },
    "teachingplan": {
        "label": "Teaching Plan",
        "path": "modules.teachingplan",
        "core": False,
        "requires": [],
        "urls": [("api/", "modules.teachingplan.urls")],
    },
    "placement": {
        "label": "Placement",
        "path": "modules.placement",
        "core": False,
        # Drive attendance creates OD requests (database link to ODRequest);
        # eligibility uses CGPA / arrears from exams.
        "requires": ["attendance", "exams"],
        "urls": [("api/placement/", "modules.placement.urls")],
    },
    "mentoring": {
        "label": "Mentoring",
        "path": "modules.mentoring",
        "core": False,
        # Mentor bands are built from CGPA (exams); mentor <-> mentee chat
        # uses messaging.
        "requires": ["exams", "messaging"],
        "urls": [("api/", "modules.mentoring.urls")],
    },
    "classgroups": {
        "label": "Class Groups",
        "path": "modules.classgroups",
        "core": False,
        "requires": [],
        "urls": [("api/", "modules.classgroups.urls")],
    },
    # WAVE 2: surveys (course-end feedback, NAAC student satisfaction, staff feedback)
    "surveys": {
        "label": "Surveys & Feedback",
        "path": "modules.surveys",
        "core": False,
        "requires": [],
        "urls": [("api/surveys/", "modules.surveys.urls")],
    },
    # WAVE 2: NAAC / NBA accreditation reports. Read-only, no tables of its own.
    # Each report checks for its source module, so none of them is "required".
    "accreditation": {
        "label": "Accreditation reports (NAAC / NBA)",
        "path": "modules.accreditation",
        "core": False,
        "requires": [],
        "urls": [("api/accreditation/", "modules.accreditation.urls")],
    },
}


def resolve_enabled(raw_value):
    """
    Turn the ENABLED_MODULES text from .env into the final, checked list of
    module names, in registry order. Core modules are always added.

    Raises ImproperlyConfigured (the server will not start) when:
      - a module name is misspelled / unknown
      - a module is turned on but something it needs is turned off
    """
    raw_value = (raw_value or "").strip()

    if raw_value == "" or raw_value.lower() == "all":
        chosen = set(MODULES)
    elif raw_value.lower() == "none":
        chosen = set()          # core only
    else:
        chosen = {name.strip() for name in raw_value.split(",") if name.strip()}
        unknown = sorted(chosen - set(MODULES))
        if unknown:
            raise ImproperlyConfigured(
                f"ENABLED_MODULES has unknown module(s): {', '.join(unknown)}. "
                f"Valid names: {', '.join(n for n, i in MODULES.items() if not i['core'])}"
            )

    chosen |= {name for name, info in MODULES.items() if info["core"]}

    problems = []
    for name in sorted(chosen):
        missing = [dep for dep in MODULES[name]["requires"] if dep not in chosen]
        if missing:
            problems.append(f"'{name}' needs: {', '.join(missing)}")
    if problems:
        raise ImproperlyConfigured(
            "ENABLED_MODULES is missing modules that others need -> "
            + "; ".join(problems)
            + ". Add them to ENABLED_MODULES in backend/.env."
        )

    return [name for name in MODULES if name in chosen]


def installed_apps_for(enabled):
    """Python paths for INSTALLED_APPS, e.g. 'modules.attendance'."""
    return [MODULES[name]["path"] for name in enabled]


# =====================================================================
# Helpers for OPTIONAL links between modules
# =====================================================================

def module_enabled(name):
    """
    Is this module switched on for this college?

        from config.module_registry import module_enabled
        if module_enabled("attendance"):
            ...
    """
    from django.conf import settings
    return name in settings.ENABLED_MODULES


def optional_function(module, dotted_path, fallback):
    """
    Get a function from another module, or `fallback` if that module is off.

        attendance_percentage = optional_function(
            "attendance", "modules.attendance.services.attendance_percentage",
            fallback=lambda *a, **k: None,
        )
    """
    if not module_enabled(module):
        return fallback
    mod_path, attr = dotted_path.rsplit(".", 1)
    return getattr(importlib.import_module(mod_path), attr)


class _EmptyQuerySet:
    """Behaves like an always-empty queryset for READ-ONLY code."""

    def _self(self, *args, **kwargs):
        return self

    filter = exclude = all = order_by = select_related = prefetch_related = _self
    annotate = distinct = values = values_list = only = defer = using = none = _self

    def count(self):
        return 0

    def exists(self):
        return False

    def first(self):
        return None

    last = first

    def aggregate(self, *args, **kwargs):
        return {key: None for key in kwargs}

    def in_bulk(self, *args, **kwargs):
        return {}

    def get(self, *args, **kwargs):
        raise ObjectDoesNotExist("This module is switched off.")

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def __bool__(self):
        return False

    def __getitem__(self, item):
        if isinstance(item, slice):
            return []
        raise IndexError("This module is switched off.")


class _MissingModel:
    """Stand-in for a model whose module is switched off: always no rows."""
    objects = _EmptyQuerySet()
    DoesNotExist = ObjectDoesNotExist


def optional_model(module, app_label, model_name):
    """
    Get a model from another module, or an always-empty stand-in if that
    module is off. Use ONLY for reading (filter / count / loop). Writing to
    a switched-off module must be guarded with module_enabled() instead.

        SemesterResult = optional_model("exams", "exams", "SemesterResult")
        for r in SemesterResult.objects.filter(student=s):   # no rows if exams is off
            ...
    """
    if not module_enabled(module):
        return _MissingModel
    from django.apps import apps
    return apps.get_model(app_label, model_name)
