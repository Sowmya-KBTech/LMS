"""
PHASE 5, PART 2 - who may open WHICH uploaded file, inside one college.

Phase 4 made sure a file opens only at its own college and only when signed
in. This file decides, for one particular file, whether THIS person may see
it: Student B may not open Student A's medical proof, submission or offer
letter, even with the exact link.

How it works
  1. The folder at the start of the file's name says which kind of upload it
     is (student_photos/, od_proofs/, ...).
  2. We find the record(s) that point to that exact file.
  3. That kind's rule says who may open it.
A file whose folder has no rule, or that no record points to, is closed to
everyone except a college admin (default deny), so a forgotten rule fails
safe instead of leaking.

Private message attachments are the one exception to "admins see all": only
the two people in the conversation may open them.
"""
from django.apps import apps

from core.permissions import is_college_admin


# ---------------------------------------------------------------- who is who
def _admin(user):
    return is_college_admin(user)


def _is_parent_of(user, student_id):
    if getattr(user, "role", None) != "parent" or student_id is None:
        return False
    profile = getattr(user, "parent_profile", None)
    return profile is not None and profile.children.filter(id=student_id).exists()


def _is_hod_of_department(user, department_id):
    if department_id is None or getattr(user, "role", None) != "teacher":
        return False
    from core.users.acting_hod import hod_department_ids
    return department_id in set(hod_department_ids(user))


def _is_tutor_of(user, student):
    if student is None or getattr(user, "role", None) != "teacher":
        return False
    from core.academics.models import YearTutor
    return YearTutor.objects.filter(
        teacher=user, course_id=student.course_id, year__year_number=student.year).exists()


def _is_staff(user):
    return _admin(user) or getattr(user, "role", None) in ("teacher", "non_teaching")


def _subject_people(user, ta):
    """The teacher of a subject-class, the HOD of its department, or an admin."""
    if ta is None:
        return _admin(user)
    if _admin(user) or ta.teacher_id == user.id:
        return True
    dept_id = getattr(ta.subject, "department_id", None) if ta.subject_id else None
    return _is_hod_of_department(user, dept_id)


def _enrolled(user, ta):
    if ta is None or getattr(user, "role", None) != "student":
        return False
    from core.academics.models import Enrollment
    return Enrollment.objects.filter(student=user, teaching_assignment=ta).exists()


# ---------------------------------------------------------------- the rules
def _student_photo(user, rec):
    s = rec.user
    return (user.id == s.id or _is_parent_of(user, s.id) or _is_staff(user))


def _staff_photo(user, rec):
    return True                                      # staff directory: anyone signed in here


def _faculty_proof(user, rec):
    t = rec.faculty
    return (user.id == t.id or _admin(user)
            or getattr(user, "sub_role", "") == "iqac_admin"
            or _is_hod_of_department(user, t.department_id))


def _subject_file(attr):
    """Lecture video, assignment question file, study material."""
    def rule(user, rec):
        ta = getattr(rec, attr)
        return _subject_people(user, ta) or _enrolled(user, ta)
    return rule


def _submission(user, rec):
    s = rec.student
    ta = rec.assignment.teaching_assignment if rec.assignment_id else None
    return (user.id == s.id or _is_parent_of(user, s.id) or _subject_people(user, ta)
            or _is_hod_of_department(user, s.department_id))


def _od_proof(user, rec):
    s = rec.student
    return (user.id == s.id or _is_parent_of(user, s.id) or _admin(user)
            or user.id in (rec.tutor_reviewed_by_id, rec.hod_reviewed_by_id)
            or _is_tutor_of(user, s) or _is_hod_of_department(user, s.department_id))


def _staff_leave_proof(user, rec):
    return (user.id in (rec.teacher_id, rec.hod_id, rec.decided_by_id) or _admin(user)
            or _is_hod_of_department(user, rec.department_id))


def _offer_letter(user, rec):
    s = rec.application.student
    return (user.id == s.id or _is_parent_of(user, s.id) or _admin(user))


def _private_message(user, rec):
    return user.id in (rec.sender_id, rec.receiver_id)      # nobody else, not even an admin


def _class_group_file(user, rec):
    group = rec.group
    if _admin(user) or group.owner() == user:
        return True
    return group.students().filter(id=user.id).exists()


def _staff_document(user, rec):          # HRIS PART A
    from core.users.hris import can_open_document
    return can_open_document(user, rec)


# folder -> (app label, model, file field, rule). Each rule decides about admins itself.
RULES = [
    ("student_photos/",      "users",      "StudentProfile",      "photo",        _student_photo),
    ("staff_photos/",        "users",      "FacultyProfile",      "photo",        _staff_photo),
    ("staff_documents/",     "users",      "StaffDocument",       "file",         _staff_document),
    ("faculty_proofs/",      "users",      "FacultyParticipation", "proof",       _faculty_proof),
    ("lectures/",            "learning",   "Lecture",             "video",        _subject_file("teaching_assignment")),
    ("assignments/",         "learning",   "Assignment",          "file",         _subject_file("teaching_assignment")),
    ("study_materials/",     "learning",   "StudyMaterial",       "file",         _subject_file("teaching_assignment")),
    ("submissions/",         "learning",   "Submission",          "file",         _submission),
    ("od_proofs/",           "attendance", "ODRequest",           "proof",        _od_proof),
    ("staff_leave_proofs/",  "attendance", "StaffLeaveRequest",   "proof",        _staff_leave_proof),
    ("student_leave_proofs/", "attendance", "StudentLeaveRequest", "proof",       _od_proof),   # WAVE 1: same people as an OD proof
    ("offer_letters/",       "placement",  "Offer",               "offer_letter", _offer_letter),
    ("private_messages/",    "messaging",  "ConversationMessage", "attachment",   _private_message),
    ("class_groups/",        "classgroups", "ClassMessage",       "attachment",   _class_group_file),
]


def can_open(user, name):
    """
    May `user` open the uploaded file stored as `name` (e.g. "od_proofs/x.pdf")
    in the CURRENT college? Default: no.
    """
    for prefix, app_label, model_name, field, rule in RULES:
        if not name.startswith(prefix):
            continue
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:            # that module is switched off for this product
            return False
        for rec in model.objects.filter(**{field: name})[:20]:
            if rule(user, rec):
                return True
        return False                   # no record grants it (or no record points to it)
    # a folder no rule knows about: admin only
    return _admin(user)
