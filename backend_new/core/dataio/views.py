"""
Import & Export API - one set of endpoints for every importer.

  GET  /api/dataio/                         importers this user may use
  GET  /api/dataio/<key>/template/          empty Excel template (+ Instructions sheet)
  GET  /api/dataio/<key>/export/            the data as Excel (?type=csv for CSV)
                                            filters are importer-specific query params
  GET  /api/dataio/<key>/history/           last 20 imports (audit)
  POST /api/dataio/<key>/start/             file + mode + commit=false -> row-by-row check
                                            file + mode + commit=true  -> saves all or nothing
                                            run by the Celery worker -> 202 {job_id};
                                            poll /api/jobs/<id>/ for the report
  (The old waiting preview/ and import/ URLs were removed on 20-11-2026.)
"""

import datetime

from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import registry
from .engine import OptionError
from .files import FileError, read_upload, write_csv, write_xlsx
from .models import ImportLog

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _importer_or_error(request, key):
    imp = registry.get(key)
    if imp is None:
        return None, Response({"detail": "Unknown import."}, status=404)
    if not imp.can_use(request.user):
        return None, Response({"detail": "You don't have permission for this import."}, status=403)
    return imp, None


def _options(request, imp, source):
    """The page's selection -> checked objects. Returns (options, error_response)."""
    raw = {k: source.get(k) for k in imp.option_keys if source.get(k) not in (None, "")}
    try:
        return imp.resolve_options(request.user, raw), None
    except OptionError as e:
        return None, Response({"detail": e.message}, status=e.status)


def _download(content, filename, content_type):
    resp = HttpResponse(content, content_type=content_type)
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp["Access-Control-Expose-Headers"] = "Content-Disposition"
    return resp


# ===================== LIST =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def importer_list(request):
    return Response([
        {"key": i.key, "label": i.label, "description": i.description,
         "match_label": i.match_label, "modes": list(i.modes)}
        for i in registry.available_for(request.user)
    ])


# ===================== TEMPLATE =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def template(request, key):
    imp, err = _importer_or_error(request, key)
    if err:
        return err
    options, err = _options(request, imp, request.query_params)
    if err:
        return err
    headers = [c.header() for c in imp.columns]
    rows = imp.template_rows(request.user, options)
    try:
        content = write_xlsx(imp.label, headers, rows, imp.instructions(), text_rows=max(500, len(rows) + 50))
    except FileError as e:
        return Response({"detail": str(e)}, status=500)
    return _download(content, f"{imp.file_name(options)}-template.xlsx", XLSX)


# ===================== EXPORT =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export(request, key):
    imp, err = _importer_or_error(request, key)
    if err:
        return err
    # "type" picks the file type; "format" can't be used - DRF reserves it
    params = {k: v for k, v in request.query_params.items()
              if k not in ("type", "format") and v not in ("", "all", None)}
    options, err = _options(request, imp, request.query_params)
    if err:
        return err
    rows = []
    for obj in imp.export_queryset(request.user, params, options):
        r = imp.export_row(obj)
        rows.append([r.get(c.key, "") for c in imp.columns])

    headers = [c.label for c in imp.columns]   # plain labels - the file imports straight back
    stamp = datetime.date.today().strftime("%d-%m-%Y")
    if request.query_params.get("type") == "csv":
        return _download(write_csv(headers, rows), f"{imp.file_name(options)}-{stamp}.csv", "text/csv")
    try:
        content = write_xlsx(imp.label, headers, rows)
    except FileError as e:
        return Response({"detail": str(e)}, status=500)
    return _download(content, f"{imp.file_name(options)}-{stamp}.xlsx", XLSX)


# ===================== STEP 7.1: PREVIEW / IMPORT AS A BACKGROUND JOB =====================
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start(request, key):
    """
    Upload an Excel/CSV file to check (commit=false) or save (commit=true).
    (The old waiting preview/ and import/ URLs were removed - lead's decision 20-11-2026.)
      202 {"job_id", "status"}  -> poll GET /api/jobs/<job_id>/ ; result = the usual report
      409 an import of this type is already running (only for commit=true)
      503 the background service (Redis) is not reachable
    """
    from modules.automation.background import JobAlreadyRunning, mark_failed, start_job
    from .tasks import rows_to_json, run_import

    imp, err = _importer_or_error(request, key)
    if err:
        return err
    options, err = _options(request, imp, request.data)       # checked now, re-checked by the worker
    if err:
        return err
    blocked = imp.write_blocked(options)
    if blocked:
        return Response({"detail": blocked}, status=400)
    upload = request.FILES.get("file")
    try:
        headers, rows = read_upload(upload)
    except FileError as e:
        return Response({"file_errors": [str(e)], "rows": [], "warnings": [],
                         "counts": {"total": 0, "new": 0, "update": 0, "skip": 0, "error": 0},
                         "saved": False, "extra": []}, status=400)

    commit = str(request.data.get("commit", "")).lower() in ("1", "true", "yes")
    params = {
        "key": key,
        "commit": commit,
        "mode": request.data.get("mode", "add"),
        "file_name": getattr(upload, "name", ""),
        "options": {k: request.data.get(k) for k in imp.option_keys
                    if request.data.get(k) not in (None, "")},
        "headers": headers,
        "rows": rows_to_json(rows),
    }
    # only one SAVE per import type at a time; checks (preview) may run side by side
    lock_key = f"dataio:{key}" if commit else ""
    try:
        job = start_job("dataio_import" if commit else "dataio_preview",
                        request.user, lock_key, params)
    except JobAlreadyRunning as e:
        return Response({"detail": f"A {imp.label} import is already running. Please wait.",
                         "job_id": str(e.job.id), "status": e.job.status}, status=409)
    try:
        run_import.delay(str(job.id))
    except Exception:
        mark_failed(job.id, "The background service is not available. Please try again.")
        return Response({"detail": "The background service is not available. Please try again.",
                         "job_id": str(job.id)}, status=503)
    job.refresh_from_db(fields=["status"])
    return Response({"job_id": str(job.id), "status": job.status}, status=202)


# ===================== HISTORY (audit) =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def history(request, key):
    imp, err = _importer_or_error(request, key)
    if err:
        return err
    logs = ImportLog.objects.filter(importer=key).select_related("imported_by")[:20]
    return Response([
        {
            "id": l.id,
            "file_name": l.file_name,
            "mode": l.get_mode_display(),
            "rows_total": l.rows_total,
            "created_count": l.created_count,
            "updated_count": l.updated_count,
            "imported_by": (l.imported_by.first_name or l.imported_by.username) if l.imported_by else "",
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ])