"""
Students & Staff import / export.

Every row is saved through core.users.serializers.UserSerializer - the same
code the Add/Edit User form uses - so nothing is duplicated:
  - email / username uniqueness checks
  - roll number / employee ID generated automatically (User.save)
  - profile details saved (StudentProfile / FacultyProfile)
  - parent account created or linked from the parent email (students)
  - subjects enrolled, and re-enrolled when course/year/semester changes

New accounts get a random password and must change it at first login.
The passwords are returned ONCE in the import result so the admin can
download the login details; they are never stored anywhere else.
"""

import secrets

from core.users.models import Department, User

from .. import fields as F
from ..engine import Importer, RowError
from ..registry import register


# ===================== WHO MAY IMPORT USERS =====================
def can_manage_users(user):
    """Super admin and academic admin (same people who manage users)."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return user.role == "admin" and (user.sub_role or "") in ("", "super_admin", "academic_admin")


def new_password(length=8):
    """Random password without look-alike characters (0/O, 1/l)."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _digits(n, name):
    def _p(text):
        t = text.replace(" ", "").replace("-", "")
        if t.startswith("+91"):
            t = t[3:]
        if not (t.isdigit() and len(t) == n):
            raise F.CellError(f"{name} must be {n} digits")
        return t
    return _p


def _serializer_errors(errors, prefix=""):
    """Flatten DRF errors into readable lines."""
    out = []
    for field, msgs in errors.items():
        if isinstance(msgs, dict):
            out.extend(_serializer_errors(msgs, prefix=f"{field}."))
            continue
        label = (prefix + field).replace("_", " ").capitalize()
        for m in (msgs if isinstance(msgs, list) else [msgs]):
            out.append(f"{label}: {m}")
    return out


class _UserImporter(Importer):
    """Shared save/check logic for students and staff."""

    role_family = ()            # roles this importer may touch

    def can_use(self, user):
        return can_manage_users(user)

    def prepare(self, user, options=None):
        from core.academics.models import Course
        return {
            "departments": F.Lookup(Department.objects.all(), "name", "code", name="department"),
            "courses": F.Lookup(Course.objects.all(), "name", name="course"),
            "existing": {
                str(getattr(u, self.match_column)).strip().lower(): u
                for u in User.objects.exclude(**{f"{self.match_column}__isnull": True})
                .exclude(**{self.match_column: ""})
            },
        }

    def find_existing(self, values, ctx):
        key = values.get(self.match_column)
        if not key:
            return None
        u = ctx["existing"].get(str(key).strip().lower())
        if u is None:
            raise F.CellError(
                f"{self.match_label.capitalize()} '{key}' not found. "
                f"Leave it blank to add a new person (it's generated automatically)."
            )
        if u.role not in self.role_family:
            raise F.CellError(f"{self.match_label.capitalize()} '{key}' belongs to a {u.get_role_display()} account")
        return u

    def unique_in_file(self):
        return [self.match_column, "username", "email"]

    def row_title(self, values, existing):
        return values.get("first_name") or values.get("username") or (existing.first_name or existing.username if existing else "")

    def check_lookups(self, values, existing, ctx):
        msgs = []
        for key, lookup in (("department", "departments"), ("course", "courses")):
            if key in values:
                try:
                    ctx[lookup].find(values[key])
                except F.CellError as e:
                    msgs.append(str(e))
        if "year" in values or "semester" in values:
            try:
                F.semester_fits_year(values.get("year", existing.year if existing else None),
                                     values.get("semester", existing.semester if existing else None))
            except F.CellError as e:
                msgs.append(str(e))
        return msgs

    # ---- build the serializer payload; run its validation without saving ----
    def build_payload(self, values, existing, ctx):
        raise NotImplementedError

    def check_row(self, values, existing, ctx, user):
        data = self.build_payload(values, existing, ctx)
        from core.users.serializers import UserSerializer
        s = UserSerializer(existing, data=data, partial=existing is not None)
        if not s.is_valid():
            raise RowError(_serializer_errors(s.errors))
        return data

    def save_row(self, payload, existing, ctx, user):
        from core.users.serializers import UserSerializer
        data = dict(payload)
        password = None
        if existing is None:
            password = new_password()
            data["password"] = password

        s = UserSerializer(existing, data=data, partial=existing is not None)
        if not s.is_valid():                       # re-checked inside the transaction
            raise RowError(_serializer_errors(s.errors))
        u = s.save()

        if existing is None:
            u.must_change_password = True          # first login asks for a new password
            u.save(update_fields=["must_change_password"])
            return {
                "name": u.first_name or u.username,
                "username": u.username,
                "id_number": u.roll_number or u.employee_id or "",
                "email": u.email,
                "password": password,
            }
        return None


# ===================== STUDENTS =====================
class StudentImporter(_UserImporter):
    key = "students"
    label = "Students"
    description = "Add new students or update existing ones. Subjects are enrolled automatically."
    file_stem = "students"
    match_column = "roll_number"
    match_label = "roll number"
    role_family = ("student",)

    columns = [
        F.roll_number(),
        F.Column("username", "Username", "add", "aarthi.r", "Login name. Must be unique."),
        F.Column("first_name", "Name", False, "Aarthi R", "Full name as it should appear."),
        F.Column("email", "Email", "add", "aarthi@example.com", "Must be unique.", F.parse_email),
        F.department("add"),
        F.course("add"),
        F.year("add"),
        F.semester("add"),
        F.batch_year(),
        F.Column("gender", "Gender", False, "Female", "Male, Female or Other.", F.parse_choice(F.GENDERS, "gender")),
        F.date_col("date_of_birth", "Date of birth"),
        F.Column("blood_group", "Blood group", False, "O+", "A+, A-, B+, B-, O+, O-, AB+, AB-.", F.parse_choice(F.BLOOD_GROUPS, "blood group")),
        F.Column("address_line1", "Address", False, "12, Gandhi Street"),
        F.Column("city", "City", False, "Vellore"),
        F.Column("district", "District", False, "Vellore"),
        F.Column("state", "State", False, "Tamil Nadu"),
        F.Column("pincode", "Pincode", False, "632001", "6 digits.", _digits(6, "Pincode")),
        F.date_col("admission_date", "Admission date", "01-08-2025"),
        F.Column("parent_name", "Parent name", False, "Ramesh K", "A parent account is created from the parent email."),
        F.Column("parent_email", "Parent email", False, "ramesh@example.com",
                 "Used as the parent's login. Brothers/sisters with the same parent email share one parent account.", F.parse_email),
        F.Column("parent_phone", "Parent phone", False, "9876543210", "10-digit mobile number.", _digits(10, "Parent phone")),
        F.Column("parent_relation", "Parent relation", False, "Father", "Father, Mother or Guardian.",
                 F.parse_choice({"father": "Father", "mother": "Mother", "guardian": "Guardian"}, "relation")),
        F.Column("parent_occupation", "Parent occupation", False, "Farmer"),
    ]

    PROFILE_KEYS = ("gender", "date_of_birth", "blood_group", "address_line1", "city",
                    "district", "state", "pincode", "admission_date")

    def build_payload(self, values, existing, ctx):
        data = {}
        for k in ("username", "first_name", "email", "year", "semester", "batch_year"):
            if k in values:
                data[k] = values[k]
        if existing is None:
            data["role"] = "student"
        if "department" in values:
            data["department"] = ctx["departments"].find(values["department"]).id
        if "course" in values:
            data["course"] = ctx["courses"].find(values["course"]).id

        # Year and semester must agree - using the saved value for whichever
        # one this row leaves blank.
        y = values.get("year", existing.year if existing else None)
        s = values.get("semester", existing.semester if existing else None)
        F.semester_fits_year(y, s)

        profile = {}
        for k in self.PROFILE_KEYS:
            if k in values:
                v = values[k]
                profile[k] = v.isoformat() if hasattr(v, "isoformat") else v
        # parent details: UserSerializer creates/links the parent account
        # (on update only when the student has no parent yet)
        if "parent_email" in values:
            profile["guardian_email"] = values["parent_email"]
        if "parent_name" in values:
            profile["father_name"] = values["parent_name"]   # the serializer reads the name from father_name
        if "parent_phone" in values:
            profile["guardian_phone"] = values["parent_phone"]
        if "parent_relation" in values:
            profile["relation"] = values["parent_relation"]
        if "parent_occupation" in values:
            profile["occupation"] = values["parent_occupation"]
        if profile:
            data["profile"] = profile
        return data

    # ---------- export ----------
    def export_queryset(self, user, params, options=None):
        qs = (User.objects.filter(role="student")
              # N+1 FIX: student_profile here too (was 1 extra query per student)
              .select_related("department", "course", "student_profile")
              .prefetch_related("parents__user")
              .order_by("roll_number", "username"))
        if params.get("department"):
            qs = qs.filter(department_id=params["department"])
        if params.get("course"):
            qs = qs.filter(course_id=params["course"])
        if params.get("year"):
            qs = qs.filter(year=params["year"])
        if params.get("semester"):
            qs = qs.filter(semester=params["semester"])
        return qs

    def export_row(self, u):
        p = getattr(u, "student_profile", None)
        parent = u.parents.all()[0] if u.parents.all() else None
        return {
            "roll_number": u.roll_number or "",
            "username": u.username,
            "first_name": u.first_name,
            "email": u.email,
            "department": u.department.name if u.department else "",
            "course": u.course.name if u.course else "",
            "year": u.year or "",
            "semester": u.semester or "",
            "batch_year": u.batch_year or "",
            "gender": p.gender if p else "",
            "date_of_birth": F.format_date(p.date_of_birth) if p else "",
            "blood_group": p.blood_group if p else "",
            "address_line1": p.address_line1 if p else "",
            "city": p.city if p else "",
            "district": p.district if p else "",
            "state": p.state if p else "",
            "pincode": p.pincode if p else "",
            "admission_date": F.format_date(p.admission_date) if p else "",
            "parent_name": (parent.user.first_name or "") if parent else "",
            "parent_email": (parent.user.email or "") if parent else "",
            "parent_phone": parent.phone if parent else "",
            "parent_relation": parent.relation if parent else "",
            "parent_occupation": parent.occupation if parent else "",
        }


# ===================== STAFF =====================
TEACHER_SUB_ROLES = ("assistant_professor", "associate_professor", "professor")
NON_TEACHING_SUB_ROLES = ("office_assistant", "lab_technician", "librarian", "clerk")


def _sub_role_options():
    labels = dict(User.SUB_ROLE_CHOICES)
    opts = {}
    for value in TEACHER_SUB_ROLES + NON_TEACHING_SUB_ROLES:
        opts[value] = value
        opts[labels[value].lower()] = value
    return opts


# Employment type: labels / short forms the office may type -> stored value
EMPLOYMENT_TYPES = {
    "permanent": "permanent", "regular": "permanent",
    "probation": "probation", "on probation": "probation",
    "contract": "contract", "contractual": "contract",
    "visiting": "visiting", "guest": "visiting", "visiting / guest": "visiting", "visiting/guest": "visiting",
}


class StaffImporter(_UserImporter):
    """
    Teachers and non-teaching staff. Admin accounts are deliberately NOT
    importable - they are created one at a time from Add User.
    """
    key = "staff"
    label = "Staff"
    description = "Add or update teachers and non-teaching staff. Admin accounts are added one at a time from Add User."
    file_stem = "staff"
    match_column = "employee_id"
    match_label = "employee ID"
    role_family = ("teacher", "non_teaching")

    columns = [
        F.employee_id(),
        F.Column("username", "Username", "add", "veni.m", "Login name. Must be unique."),
        F.Column("first_name", "Name", False, "Veni M", "Full name as it should appear."),
        F.Column("email", "Email", "add", "veni@example.com", "Must be unique.", F.parse_email),
        F.Column("role", "Staff type", "add", "Teacher", "Teacher or Non-teaching.",
                 F.parse_choice({"teacher": "teacher", "non-teaching": "non_teaching", "non teaching": "non_teaching",
                                 "non_teaching": "non_teaching", "non-teaching staff": "non_teaching"}, "staff type", "Teacher or Non-teaching")),
        F.Column("sub_role", "Designation", False, "Assistant Professor",
                 "Teachers: Assistant Professor, Associate Professor, Professor. "
                 "Non-teaching: Office Assistant, Lab Technician, Librarian, Clerk.",
                 F.parse_choice(_sub_role_options(), "designation",
                                "Assistant Professor, Associate Professor, Professor, Office Assistant, Lab Technician, Librarian or Clerk")),
        F.department("add"),
        F.Column("gender", "Gender", False, "Female", "Male, Female or Other.", F.parse_choice(F.GENDERS, "gender")),
        F.date_col("date_of_birth", "Date of birth", "21-03-1988"),
        F.Column("blood_group", "Blood group", False, "B+", "A+, A-, B+, B-, O+, O-, AB+, AB-.", F.parse_choice(F.BLOOD_GROUPS, "blood group")),
        F.Column("qualification", "Qualification", False, "M.E., Ph.D."),
        F.Column("specialization", "Specialization", False, "Thermal Engineering"),
        F.date_col("date_of_joining", "Date of joining", "15-06-2015"),
        F.Column("experience_years", "Experience (years)", False, "10", "Whole number.", F.parse_int(0, 60, "experience")),
        # Staff records counts a profile as incomplete without these (core/users/hris.py -> _missing)
        F.Column("employment_type", "Employment type", False, "Permanent",
                 "Permanent, On probation, Contract or Visiting.", F.parse_choice(EMPLOYMENT_TYPES, "employment type",
                                                                                 "Permanent, On probation, Contract or Visiting")),
        F.Column("aicte_id", "AICTE ID", False, "1-1234567890", "AICTE faculty ID, if the college records it."),
        F.Column("city", "City", False, "Vellore"),
        F.Column("state", "State", False, "Tamil Nadu"),
    ]

    PROFILE_KEYS = ("gender", "date_of_birth", "blood_group", "qualification", "specialization",
                    "date_of_joining", "experience_years", "employment_type", "aicte_id", "city", "state")

    def build_payload(self, values, existing, ctx):
        data = {}
        for k in ("username", "first_name", "email", "role", "sub_role"):
            if k in values:
                data[k] = values[k]
        if "department" in values:
            data["department"] = ctx["departments"].find(values["department"]).id

        role = values.get("role", existing.role if existing else None)
        sub = values.get("sub_role", existing.sub_role if existing else None)
        if sub and role == "teacher" and sub not in TEACHER_SUB_ROLES:
            raise RowError(["Designation doesn't match a teacher (use Assistant Professor, Associate Professor or Professor)"])
        if sub and role == "non_teaching" and sub not in NON_TEACHING_SUB_ROLES:
            raise RowError(["Designation doesn't match non-teaching staff (use Office Assistant, Lab Technician, Librarian or Clerk)"])

        profile = {}
        for k in self.PROFILE_KEYS:
            if k in values:
                v = values[k]
                profile[k] = v.isoformat() if hasattr(v, "isoformat") else v
        if profile:
            data["profile"] = profile
        return data

    def export_queryset(self, user, params, options=None):
        qs = (User.objects.filter(role__in=self.role_family)
              # N+1 FIX: faculty_profile here too (was 1 extra query per person)
              .select_related("department", "faculty_profile")
              .order_by("employee_id", "username"))
        if params.get("department"):
            qs = qs.filter(department_id=params["department"])
        if params.get("role") in self.role_family:
            qs = qs.filter(role=params["role"])
        return qs

    def export_row(self, u):
        p = getattr(u, "faculty_profile", None)
        return {
            "employee_id": u.employee_id or "",
            "username": u.username,
            "first_name": u.first_name,
            "email": u.email,
            "role": "Teacher" if u.role == "teacher" else "Non-teaching",
            "sub_role": u.get_sub_role_display() if u.sub_role else "",
            "department": u.department.name if u.department else "",
            "gender": p.gender if p else "",
            "date_of_birth": F.format_date(p.date_of_birth) if p else "",
            "blood_group": p.blood_group if p else "",
            "qualification": p.qualification if p else "",
            "specialization": p.specialization if p else "",
            "date_of_joining": F.format_date(p.date_of_joining) if p else "",
            "experience_years": p.experience_years if p and p.experience_years is not None else "",
            "employment_type": p.get_employment_type_display() if p and p.employment_type else "",
            "aicte_id": p.aicte_id if p else "",
            "city": p.city if p else "",
            "state": p.state if p else "",
        }


register(StudentImporter())
register(StaffImporter())