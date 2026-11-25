"""
COMMON FIELDS - one definition for columns that appear in many imports.

The senior review asked for "repeated fields aligned across the app". This
file is that alignment: every importer builds its columns from these, so a
roll number, a department, a semester or a date is named, written and
checked the SAME way in every template, export and import.

Formats used everywhere
  Roll number     21ME001           (as stored; matched without case)
  Employee ID     TCH001
  Department      name OR code      ("Mechanical" or "ME")
  Course          exact course name ("B.E Mechanical")
  Year            1-4
  Semester        1-8, and must belong to the year (Year 2 -> Sem 3 or 4)
  Batch year      4 digits          (2025)
  Dates           DD-MM-YYYY        (also accepts DD/MM/YYYY, YYYY-MM-DD
                                     and real Excel date cells)
  Academic year   2026-2027
"""

import datetime
import re


class CellError(ValueError):
    """A cell's value is not valid. The message is shown to the user."""


# ===================== COLUMN =====================
class Column:
    """
    One column in a template / export / import.

    required:  False   - optional
               "add"   - required when a NEW record is created
               "always"- required on every row
    """

    def __init__(self, key, label, required=False, example="", help="", parse=None, choices=None):
        self.key = key
        self.label = label
        self.required = required
        self.example = example
        self.help = help
        self.parse = parse          # function(text) -> python value, raises CellError
        self.choices = choices      # shown in the template's Instructions sheet

    def header(self):
        """Header text written in templates and exports."""
        return f"{self.label} *" if self.required else self.label


# ===================== NORMALISING HEADERS =====================
def norm_header(text):
    """
    'Date of birth (DD-MM-YYYY) *'  ->  'date_of_birth'
    'Roll number'                   ->  'roll_number'
    Lets users upload files whose headers use either the label or the key.
    """
    t = str(text or "").strip().lower()
    t = re.sub(r"\(.*?\)", "", t)          # drop "(DD-MM-YYYY)" hints
    t = t.replace("*", "")
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t


# ===================== CELL PARSERS =====================
def as_text(value):
    """Every cell arrives as text (or a date from Excel); trim it."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)                  # Excel turns 2025 into 2025.0
    return str(value).strip()


def parse_int(lo=None, hi=None, name="number"):
    def _p(text):
        try:
            n = int(float(text))
        except (TypeError, ValueError):
            raise CellError(f"'{text}' is not a {name}")
        if lo is not None and n < lo or hi is not None and n > hi:
            raise CellError(f"{name.capitalize()} must be between {lo} and {hi}")
        return n
    return _p


def parse_half(lo=0, hi=None, name="number"):
    """A whole or half number: 3, 4, 1.5 (WAVE 3: credits). Returns a Decimal."""
    from decimal import Decimal, InvalidOperation

    def _p(text):
        try:
            d = Decimal(str(text).strip())
        except (InvalidOperation, ValueError):
            raise CellError(f"'{text}' is not a {name}")
        if (d * 2) != (d * 2).to_integral_value():
            raise CellError(f"{name.capitalize()} must be whole or half (like 3 or 1.5)")
        if lo is not None and d < lo or hi is not None and d > hi:
            raise CellError(f"{name.capitalize()} must be between {lo} and {hi}")
        return d
    return _p


DATE_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y")


def parse_date(text):
    if isinstance(text, datetime.datetime):
        return text.date()
    if isinstance(text, datetime.date):
        return text
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise CellError(f"'{text}' is not a date - use DD-MM-YYYY")


def parse_email(text):
    t = text.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", t):
        raise CellError(f"'{text}' is not a valid email")
    return t.lower()


def parse_choice(options, name="value", shown=None):
    """
    options: dict of accepted text (lower-case) -> stored value.
    Accepts the stored value itself or its label, without case.
    shown:   what to suggest when the value is wrong (e.g. "P, A or OD");
             defaults to the stored values.
    """
    def _p(text):
        key = str(text).strip().lower()
        if key in options:
            return options[key]
        hint = shown or ", ".join(sorted({str(v) for v in options.values() if v not in (None, "")}))
        raise CellError(f"'{text}' is not a valid {name}. Use {hint}")
    return _p


GENDERS = {"male": "Male", "m": "Male", "female": "Female", "f": "Female", "other": "Other"}
BLOOD_GROUPS = {g.lower(): g for g in ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]}


def format_date(value):
    """How dates are WRITTEN in exports: DD-MM-YYYY."""
    return value.strftime("%d-%m-%Y") if value else ""


# ===================== SHARED COLUMN DEFINITIONS =====================
# Importers pick from these (and add their own). Keys match model fields.

def roll_number(required=False, help="Leave blank for new students - it is generated automatically."):
    return Column("roll_number", "Roll number", required, "25ME001", help)


def employee_id(required=False, help="Leave blank for new staff - it is generated automatically."):
    return Column("employee_id", "Employee ID", required, "TCH001", help)


def department(required=False):
    return Column("department", "Department", required, "Mechanical",
                  "Department name or code, exactly as in Departments.")


def course(required=False):
    return Column("course", "Course", required, "B.E Mechanical",
                  "Course name, exactly as in Courses.")


def year(required=False):
    return Column("year", "Year", required, "1", "1 to 4.", parse_int(1, 4, "year"))


def semester(required=False):
    return Column("semester", "Semester", required, "1",
                  "1 to 8, and it must belong to the year (Year 1 -> 1 or 2).",
                  parse_int(1, 8, "semester"))


def batch_year(required=False):
    return Column("batch_year", "Batch year", required, "2025",
                  "Year of admission, 4 digits.", parse_int(2000, 2100, "batch year"))


def date_col(key, label, example="14-06-2007", required=False):
    return Column(key, f"{label} (DD-MM-YYYY)", required, example, "Date as DD-MM-YYYY.", parse_date)


def semester_fits_year(year_value, semester_value):
    """Year 1 -> Sem 1/2, Year 2 -> 3/4 ... (same rule as promotion)."""
    if year_value and semester_value and semester_value not in (2 * year_value - 1, 2 * year_value):
        raise CellError(
            f"Semester {semester_value} doesn't belong to Year {year_value} "
            f"(Year {year_value} is Semester {2 * year_value - 1} or {2 * year_value})"
        )


# ===================== LOOKUPS =====================
class Lookup:
    """
    Find a related row by name / code without one query per cell.
    Built once per import (prepare), then reused for every row.
    """

    def __init__(self, queryset, *fields, name="record"):
        self.name = name
        self.map = {}
        for obj in queryset:
            for f in fields:
                v = getattr(obj, f, None)
                if v:
                    self.map[str(v).strip().lower()] = obj

    def find(self, text):
        if not text:
            return None
        obj = self.map.get(text.strip().lower())
        if obj is None:
            raise CellError(f"{self.name.capitalize()} '{text}' not found")
        return obj
