"""
WAVE 2 - ACCREDITATION REPORTS API (under /api/accreditation/).

  GET reports/?year=2025&department=<id>              the 8 reports with a one-line headline each
  GET reports/<key>/?year=2025&department=<id>        one report: columns, rows, total
  GET reports/<key>/excel/?year=2025&department=<id>  the same report as an .xlsx file

year = the academic year's first year (2025 -> 2025-26); default: the current one.
department = blank for all departments.

Who
  all departments : main admin, IQAC admin, the Principal
  own department  : the HOD (the department is forced to theirs)
"""
from io import BytesIO

from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.users.models import Department

from .reports import BY_KEY, REPORTS, Scope, current_year

YEARS_BACK = 5


def _college_wide(user):
    from core.users.acting_hod import is_main_admin
    from core.users.principal import is_principal
    if is_main_admin(user):
        return True
    if getattr(user, "role", "") == "admin" and (user.sub_role or "") == "iqac_admin":
        return True
    return is_principal(user)


def _hod_depts(user):
    if getattr(user, "role", "") != "teacher":
        return []
    from core.users.acting_hod import hod_department_ids
    return list(hod_department_ids(user))


def _scope(request):
    """(Scope, allowed_departments, college_wide) or (None, error Response, None)."""
    user = request.user
    college = _college_wide(user)
    mine = [] if college else _hod_depts(user)
    if not college and not mine:
        return None, Response({"detail": "Accreditation reports are for the IQAC, the Principal, "
                                         "admins and HODs."}, status=403), None

    raw_year = request.query_params.get("year") or ""
    this_year = current_year()
    try:
        year = int(raw_year) if raw_year else this_year
    except ValueError:
        return None, Response({"detail": "year must be a number like 2025."}, status=400), None
    if not this_year - 20 <= year <= this_year:
        return None, Response({"detail": "Choose a year from the list."}, status=400), None

    allowed = Department.objects.order_by("name")
    if not college:
        allowed = allowed.filter(id__in=mine)
    raw_dept = request.query_params.get("department") or ""
    if raw_dept:
        dept = allowed.filter(id=raw_dept).first() if raw_dept.isdigit() else None
        if dept is None:
            return None, Response({"detail": "You can't see reports for that department."}, status=403), None
    elif college:
        dept = None
    else:
        dept = allowed.first()                  # an HOD always sees their own department
    return Scope(year=year, department=dept), list(allowed), college


def _meta(scope, allowed, college):
    this_year = current_year()
    return {
        "year": scope.year, "year_label": scope.label,
        "from": scope.start, "to": scope.end,
        "department": scope.department.id if scope.department else None,
        "department_name": scope.department.name if scope.department else "All departments",
        "college_wide": college,
        "departments": [{"id": d.id, "name": d.name} for d in allowed],
        "years": [{"year": y, "label": f"{y}-{str(y + 1)[-2:]}"} for y in range(this_year, this_year - YEARS_BACK, -1)],
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_list(request):
    scope, allowed, college = _scope(request)
    if scope is None:
        return allowed
    cards = []
    for key, fn in REPORTS:
        r = fn(scope)
        cards.append({"key": key, "title": r["title"], "supports": r["supports"], "headline": r["headline"],
                      "available": r["available"], "rows": len(r["rows"])})
    return Response({**_meta(scope, allowed, college), "reports": cards})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_detail(request, key):
    fn = BY_KEY.get(key)
    if fn is None:
        return Response({"detail": "No such report."}, status=404)
    scope, allowed, college = _scope(request)
    if scope is None:
        return allowed
    return Response({**_meta(scope, allowed, college), "report": fn(scope)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_excel(request, key):
    fn = BY_KEY.get(key)
    if fn is None:
        return Response({"detail": "No such report."}, status=404)
    scope, allowed, college = _scope(request)
    if scope is None:
        return allowed
    report = fn(scope)
    data = build_xlsx(report, scope, getattr(request, "tenant", None))
    dept = (scope.department.code or scope.department.name) if scope.department else "All"
    name = f"{report['key']}_{scope.label}_{dept}.xlsx".replace(" ", "-").replace("/", "-")
    resp = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp


def build_xlsx(report, scope, tenant=None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = report["title"][:31]
    cols = report["columns"]
    width = max(len(cols), 2)
    college = getattr(tenant, "name", "") or ""

    ws.append([college or "KB Tech Campus"])
    ws.append([report["title"]])
    ws.append([f"Academic year {scope.label} ({scope.start:%d-%m-%Y} to {scope.end:%d-%m-%Y})  ·  "
               f"{scope.department.name if scope.department else 'All departments'}"])
    ws.append([f"Supports: {report['supports']}"])
    ws.append([])
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"].font = Font(bold=True, size=12)
    for r in (3, 4):
        ws.cell(row=r, column=1).font = Font(color="555555")

    if not report["available"]:
        ws.append([report["note"]])
    else:
        head_row = ws.max_row + 1
        ws.append([c["label"] for c in cols])
        thin = Side(style="thin", color="CCCCCC")
        for i in range(1, len(cols) + 1):
            cell = ws.cell(row=head_row, column=i)
            cell.font = Font(bold=True)
            cell.fill = PatternFill("solid", fgColor="EEEAFE")
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            cell.border = Border(bottom=thin)
        for row in report["rows"]:
            ws.append([row.get(c["key"]) for c in cols])
        if report.get("total"):
            ws.append([report["total"].get(c["key"]) for c in cols])
            for i in range(1, len(cols) + 1):
                ws.cell(row=ws.max_row, column=i).font = Font(bold=True)
        ws.freeze_panes = ws.cell(row=head_row + 1, column=1)
        ws.append([])
        ws.append([f"Note: {report['note']}"])
        ws.cell(row=ws.max_row, column=1).font = Font(italic=True, color="555555")

    for i, c in enumerate(cols or [{"label": ""}] * width, 1):
        longest = max([len(str(c.get("label", "")))] + [len(str(r.get(c.get("key"), "") or ""))
                                                         for r in report["rows"][:500]])
        ws.column_dimensions[get_column_letter(i)].width = min(max(12, longest + 2), 60)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
