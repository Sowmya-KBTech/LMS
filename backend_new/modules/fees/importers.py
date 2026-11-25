"""
Fees import / export (shared engine in core/dataio).
Registered from FeesConfig.ready(), so it only exists when the fees module is on.

Import RAISES fees (or corrects the amount / due date of a fee already
raised). One row = one student + one term. It never records payments:
paid amount, balance and status are always worked out from the payment rows
(Fee.recalculate - the single source of truth), so those columns appear in
the export but are ignored when importing.

A new fee notifies the student's parents, exactly like raising it on screen
(the post_save signal on Fee).
"""

from decimal import Decimal, InvalidOperation

from core.dataio import fields as F
from core.dataio.engine import Importer, RowError
from core.users.models import Department, User

from .models import Fee


def can_manage_fees(user):
    """Super admin and accounts admin."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return user.role == "admin" and (user.sub_role or "") in ("", "super_admin", "accounts_admin")


def parse_amount(text):
    try:
        amt = Decimal(str(text).replace(",", "").replace("₹", "").strip())
    except InvalidOperation:
        raise F.CellError(f"'{text}' is not an amount")
    if amt <= 0:
        raise F.CellError("Amount must be more than 0")
    if amt != amt.quantize(Decimal("0.01")):
        raise F.CellError("Amount can have at most 2 decimal places")
    return amt


def _money(v):
    v = Decimal(v or 0)
    return int(v) if v == v.to_integral() else float(v)


class FeeImporter(Importer):
    key = "fees"
    label = "fees"
    description = "Raise fees for students, or correct the amount / due date of a fee already raised."
    file_stem = "fees"
    match_column = "roll_number"
    match_label = "roll number and term"

    columns = [
        F.Column("roll_number", "Roll number", "always", "25ME001", "Student's roll number."),
        F.Column("first_name", "Name", False, "Aarthi R", "For your reference only - not saved."),
        F.Column("term", "Term", "always", "Semester 1 Tuition Fee",
                 "What the fee is for. A student + term pair identifies the fee."),
        F.Column("amount", "Amount", "add", "45000", "In rupees.", parse_amount),
        F.date_col("due_date", "Due date", "30-09-2026", required="add"),
        F.Column("paid", "Paid", False, "", "Filled in by the export - ignored when importing."),
        F.Column("balance", "Balance", False, "", "Filled in by the export - ignored when importing."),
        F.Column("status", "Status", False, "", "Filled in by the export - ignored when importing."),
    ]

    def can_use(self, user):
        return can_manage_fees(user)

    def unique_in_file(self):
        return []          # duplicates are checked on roll number + term

    def prepare(self, user, options=None):
        students = User.objects.filter(role="student").exclude(roll_number__isnull=True).exclude(roll_number="")
        return {
            "students": {s.roll_number.strip().lower(): s for s in students},
            "fees": {(f.student_id, f.term.strip().lower()): f for f in Fee.objects.all()},
            "seen": set(),
        }

    def find_existing(self, values, ctx):
        if "roll_number" not in values or "term" not in values:
            return None
        roll = values["roll_number"]
        s = ctx["students"].get(str(roll).strip().lower())
        if s is None:
            raise F.CellError(f"Roll number '{roll}' not found")
        key = (s.id, values["term"].strip().lower())
        if key in ctx["seen"]:
            raise F.CellError("The same student and term appear more than once in the file")
        ctx["seen"].add(key)
        values["_student"] = s
        return ctx["fees"].get(key)

    def row_title(self, values, existing):
        s = values.get("_student")
        return s.display_name if s else values.get("first_name", "")

    def check_row(self, values, existing, ctx, user):
        if existing is not None and "amount" in values and values["amount"] < existing.paid_amount:
            raise RowError([f"₹{_money(existing.paid_amount)} is already paid for this fee - the amount can't be lower than that"])
        return {
            "student": values["_student"],
            "term": values["term"].strip(),
            "amount": values.get("amount"),
            "due_date": values.get("due_date"),
        }

    def save_row(self, payload, existing, ctx, user):
        if existing is None:
            Fee.objects.create(student=payload["student"], term=payload["term"],
                               amount=payload["amount"], due_date=payload["due_date"])
            return None
        changed = []
        if payload["amount"] is not None:
            existing.amount = payload["amount"]
            changed.append("amount")
        if payload["due_date"] is not None:
            existing.due_date = payload["due_date"]
            changed.append("due_date")
        if changed:
            existing.save(update_fields=changed)
            existing.recalculate()          # status follows the new amount
        return None

    # ---------- export ----------
    def export_queryset(self, user, params, options=None):
        qs = Fee.objects.select_related("student").order_by("student__roll_number", "term")
        if params.get("department"):
            qs = qs.filter(student__department_id=params["department"])
        if params.get("status") in ("pending", "partial", "paid"):
            qs = qs.filter(status=params["status"])
        if params.get("term"):
            qs = qs.filter(term__icontains=params["term"])
        return qs

    def export_row(self, f):
        return {
            "roll_number": f.student.roll_number or "",
            "first_name": f.student.display_name,
            "term": f.term,
            "amount": _money(f.amount),
            "due_date": F.format_date(f.due_date),
            "paid": _money(f.paid_amount),
            "balance": _money(Decimal(f.amount) - Decimal(f.paid_amount or 0)),
            "status": f.get_status_display(),
        }
