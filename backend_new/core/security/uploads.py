"""
UPLOAD SIZE LIMITS - one ceiling for EVERY upload in the app.

Without this, one 5 GB file could fill the server disk for every college.
Each file in a request is checked by its kind:

  video  (lecture videos)                      500 MB   VIDEO_UPLOAD_MAX_MB
  audio  (voice notes)                          25 MB   AUDIO_UPLOAD_MAX_MB
  image  (photos)                                5 MB   IMAGE_UPLOAD_MAX_MB
  anything else (PDF, Word, Excel, zip ...)     20 MB   FILE_UPLOAD_MAX_MB

A request whose total size is already above the biggest limit is refused
BEFORE it is read, so nothing is written to disk.

Screens with a smaller limit of their own keep it (message attachments 10 MB,
Excel imports 5 MB). On the server, Nginx's client_max_body_size should match
the video limit (set in the Docker step).
"""
import os

from django.conf import settings
from django.http import JsonResponse

MB = 1024 * 1024

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".wmv", ".flv", ".mpeg", ".mpg", ".3gp"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".ogg", ".oga", ".aac", ".opus", ".amr", ".flac"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif", ".svg"}

LABEL = {"video": "videos", "audio": "voice notes and audio", "image": "photos and images",
         "file": "files"}


def limits_mb():
    return {
        "video": int(getattr(settings, "VIDEO_UPLOAD_MAX_MB", 500)),
        "audio": int(getattr(settings, "AUDIO_UPLOAD_MAX_MB", 25)),
        "image": int(getattr(settings, "IMAGE_UPLOAD_MAX_MB", 5)),
        "file": int(getattr(settings, "FILE_UPLOAD_MAX_MB", 20)),
    }


def kind_of(upload):
    """video / audio / image / file - from the browser's content type, then the extension."""
    ctype = (getattr(upload, "content_type", "") or "").lower()
    ext = os.path.splitext(getattr(upload, "name", "") or "")[1].lower()
    for kind, exts in (("video", VIDEO_EXT), ("audio", AUDIO_EXT), ("image", IMAGE_EXT)):
        if ctype.startswith(kind + "/") or ext in exts:
            # ".webm" can be either: trust the content type for it
            return kind
    if ext == ".webm":
        return "video" if ctype.startswith("video/") else "audio"
    return "file"


def _too_big(detail, limit_mb):
    return JsonResponse({"detail": detail, "limit_mb": limit_mb}, status=413)


def _size_text(size):
    mb = size / MB
    return f"{mb:.1f} MB" if mb < 10 else f"{mb:.0f} MB"


class UploadLimitMiddleware:
    """Placed right after the tenant and CORS middleware (config/settings.py)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ctype = request.META.get("CONTENT_TYPE", "")
        if request.method in ("POST", "PUT", "PATCH") and ctype.startswith("multipart/form-data"):
            refused = self.check(request)
            if refused is not None:
                return refused
        return self.get_response(request)

    def check(self, request):
        limits = limits_mb()
        biggest = max(limits.values())

        # 1. Whole request far too big: refuse without reading it.
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if length > (biggest + 5) * MB:
            return _too_big(f"This upload is {_size_text(length)}. The largest file allowed is "
                            f"{biggest} MB (videos).", biggest)

        # 2. Each file by its kind. (DRF re-uses what Django parsed here.)
        for field in request.FILES:
            for upload in request.FILES.getlist(field):
                kind = kind_of(upload)
                if upload.size > limits[kind] * MB:
                    return _too_big(
                        f"\"{upload.name}\" is {_size_text(upload.size)}. The limit for "
                        f"{LABEL[kind]} is {limits[kind]} MB.", limits[kind])
        return None
