# backend/config/range_middleware.py
import os
import re
import mimetypes as _mimetypes
from django.http import FileResponse, StreamingHttpResponse
from django.conf import settings

class RangeFileMiddleware:
    CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB chunks

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only handle media file requests (videos only — not PDFs/docs)
        if not request.path.startswith('/media/'):
            return response
        
        # Skip range handling for non-video files (PDFs, images, docs)
        video_extensions = ('.mp4', '.webm', '.ogg', '.mov', '.avi')
        if not any(request.path.lower().endswith(ext) for ext in video_extensions):
            return response

        # Only handle successful responses
        if response.status_code not in (200, 206):
            return response

        # Resolve the file path on disk
        relative_path = request.path[len('/media/'):]
        file_path = os.path.join(settings.MEDIA_ROOT, relative_path)

        if not os.path.isfile(file_path):
            return response

        file_size = os.path.getsize(file_path)

        # Determine content type
        content_type, _ = _mimetypes.guess_type(file_path)
        if content_type is None:
            content_type = 'application/octet-stream'

        range_header = request.META.get('HTTP_RANGE', '').strip()

        # No Range header — return full file with Accept-Ranges hint
        if not range_header:
            response = FileResponse(
                open(file_path, 'rb'),
                content_type=content_type,
            )
            response['Accept-Ranges'] = 'bytes'
            response['Content-Length'] = file_size
            return response

        # Parse Range header: bytes=start-end
        match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if not match:
            return response

        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else file_size - 1
        end = min(end, file_size - 1)

        if start > end or start >= file_size:
            error_response = StreamingHttpResponse(status=416)
            error_response['Content-Range'] = f'bytes */{file_size}'
            return error_response

        length = end - start + 1

        def file_iterator(path, offset, chunk_size, total):
            with open(path, 'rb') as f:
                f.seek(offset)
                remaining = total
                while remaining > 0:
                    data = f.read(min(chunk_size, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        streaming_response = StreamingHttpResponse(
            file_iterator(file_path, start, self.CHUNK_SIZE, length),
            status=206,
            content_type=content_type,
        )
        streaming_response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        streaming_response['Accept-Ranges'] = 'bytes'
        streaming_response['Content-Length'] = length
        return streaming_response