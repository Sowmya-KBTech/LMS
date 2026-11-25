"""
PHASE 4 - uploaded files belong to ONE college.

Saving: settings.STORAGES uses django-tenants' TenantFileSystemStorage with
MULTITENANT_RELATIVE_MEDIA_ROOT = "%s", so an upload made at ABC is written to
    media/abc/student_photos/ravi.jpg
and its URL is
    /media/abc/student_photos/ravi.jpg
The database keeps the short name ("student_photos/ravi.jpg"); the college
part comes from the address the request arrived at.

Serving: this view replaces Django's open static() media serving. A file is
sent only when
  1. the link is inside THIS college's folder (abc.../media/xyz/... -> 404),
  2. the path stays inside that folder (no ../ tricks), and
  3. the person is signed in at this college - by the session cookie that
     login sets (what <img> and plain links carry), or by the JWT, and
  4. (PHASE 5 PART 2) this person may open THIS file - core/tenants/file_access.py.

On the server, set MEDIA_ACCEL_REDIRECT_PREFIX so Nginx sends the bytes after
Django has said yes (fast); on a laptop Django sends the file itself.
"""
import mimetypes
import os
import posixpath

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.utils._os import safe_join
from django_tenants.utils import get_public_schema_name


def _signed_in_user(request):
    """The user signed in at THIS college - by session cookie (images, links) or
    Bearer token (API calls) - or None."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user
    if request.META.get("HTTP_AUTHORIZATION", "").lower().startswith("bearer "):
        from rest_framework.exceptions import AuthenticationFailed
        from core.tenants.jwt import TenantJWTAuthentication
        try:
            result = TenantJWTAuthentication().authenticate(request)
        except AuthenticationFailed:
            return None
        return result[0] if result else None
    return None


def college_media(request, path):
    schema = connection.schema_name
    if schema == get_public_schema_name():
        raise Http404()

    # 1) only this college's folder; another college's link simply doesn't exist here
    clean = posixpath.normpath(path).lstrip("/")
    if clean.startswith("..") or clean.split("/", 1)[0] != schema or clean == schema:
        raise Http404()

    # 2) never leave MEDIA_ROOT/<this college>/
    try:
        full = safe_join(settings.MEDIA_ROOT, schema, clean.split("/", 1)[1])
    except (SuspiciousFileOperation, ValueError):
        raise Http404()

    # 3) signed in at this college
    user = _signed_in_user(request)
    if user is None:
        return JsonResponse({"detail": "Sign in to open this file."}, status=403)

    if not os.path.isfile(full):
        raise Http404()

    # 4) PHASE 5 PART 2: allowed to open THIS file (core/tenants/file_access.py)
    from core.tenants.file_access import can_open
    if not can_open(user, clean.split("/", 1)[1]):
        return JsonResponse({"detail": "You don't have access to this file."}, status=403)

    prefix = getattr(settings, "MEDIA_ACCEL_REDIRECT_PREFIX", "")
    if prefix:
        # Nginx serves the file from an `internal` location (see settings.py)
        response = HttpResponse()
        response["X-Accel-Redirect"] = prefix.rstrip("/") + "/" + clean
        response["Content-Type"] = mimetypes.guess_type(full)[0] or "application/octet-stream"
    else:
        response = FileResponse(open(full, "rb"))
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response
