"""
COLLEGE LOGO - check and clean an uploaded logo.

  * PNG, JPEG or WebP only. SVG is refused: an SVG can carry scripts.
  * The file must really be that image (opened and checked with Pillow),
    not just named .png.
  * It is resized to fit 512 x 512 and saved again as a clean PNG, which also
    drops anything hidden inside the original file.
"""
import io

from PIL import Image, UnidentifiedImageError

MAX_UPLOAD_BYTES = 2 * 1024 * 1024        # 2 MB as uploaded
MAX_SIDE = 512                            # px
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}


class LogoError(ValueError):
    pass


def clean_logo(upload):
    """Return the logo as PNG bytes, or raise LogoError with a readable reason."""
    if upload is None:
        raise LogoError("Choose an image file for the logo.")
    if upload.size > MAX_UPLOAD_BYTES:
        raise LogoError("The logo must be 2 MB or smaller.")
    data = upload.read()
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        probe.verify()                              # damaged / fake files fail here
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise LogoError("That file is not a PNG, JPEG or WebP image.")
    if fmt not in ALLOWED_FORMATS:
        raise LogoError("The logo must be a PNG, JPEG or WebP image.")

    img = img.convert("RGBA")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
