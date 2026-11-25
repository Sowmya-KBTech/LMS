"""
COLLEGE LOGO TESTS - KB Technosoft sets it in the console; the college's
login page shows it before anyone signs in.

Run:  python manage.py test core.tenants.tests_logo -v 2
"""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django_tenants.utils import schema_context
from PIL import Image

from core.tenants.models import CollegeLogo
from core.tenants.tests_platform import PLATFORM, PlatformTestBase

COLLEGE_HOST = "testserver"


def image_file(fmt="PNG", size=(900, 300), name=None, color=(200, 30, 60, 255)):
    buf = io.BytesIO()
    Image.new("RGBA" if fmt == "PNG" else "RGB", size, color[:4] if fmt == "PNG" else color[:3]).save(buf, format=fmt)
    ext = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp", "GIF": "gif"}[fmt]
    return SimpleUploadedFile(name or f"logo.{ext}", buf.getvalue(), content_type=f"image/{ext}")


class CollegeLogoTests(PlatformTestBase):

    def url(self):
        return f"/api/platform/colleges/{self.college.id}/logo/"

    def upload(self, f, token="auto"):
        token = self.platform_token() if token == "auto" else token
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        return Client(HTTP_HOST=PLATFORM).post(self.url(), {"logo": f}, **headers)

    def college_info(self):
        return Client(HTTP_HOST=COLLEGE_HOST).get("/api/college/").json()

    def test_no_logo_at_first(self):
        self.assertIsNone(self.college_info()["logo_version"])
        self.assertEqual(Client(HTTP_HOST=COLLEGE_HOST).get("/api/college/logo/").status_code, 404)

    def test_kb_sets_a_logo_and_the_login_page_gets_it_without_signing_in(self):
        r = self.upload(image_file("JPEG"))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNotNone(r.json()["logo_version"])

        info = self.college_info()
        self.assertEqual(info["logo_version"], r.json()["logo_version"])
        img = Client(HTTP_HOST=COLLEGE_HOST).get(f"/api/college/logo/?v={info['logo_version']}")
        self.assertEqual(img.status_code, 200)
        self.assertEqual(img["Content-Type"], "image/png")              # always re-saved as PNG
        self.assertIn("max-age", img["Cache-Control"])
        pic = Image.open(io.BytesIO(img.content))
        self.assertEqual(pic.format, "PNG")
        self.assertLessEqual(max(pic.size), 512)                          # resized

    def test_console_can_show_it_too(self):
        self.upload(image_file())
        r = Client(HTTP_HOST=PLATFORM).get(self.url())                   # an <img>, no token
        self.assertEqual(r.status_code, 200)

    def test_only_kb_can_change_it(self):
        self.assertEqual(self.upload(image_file(), token=None).status_code, 401)
        self.assertEqual(self.upload(image_file(), token=self.college_token()).status_code, 401)
        r = Client(HTTP_HOST=PLATFORM).delete(self.url())
        self.assertEqual(r.status_code, 401)
        with schema_context("public"):
            self.assertFalse(CollegeLogo.objects.exists())

    def test_a_college_cannot_set_its_logo_from_its_own_address(self):
        r = Client(HTTP_HOST=COLLEGE_HOST).post("/api/college/logo/", {"logo": image_file()},
                                                HTTP_AUTHORIZATION=f"Bearer {self.college_token()}")
        self.assertEqual(r.status_code, 405)

    def test_bad_files_are_refused(self):
        svg = SimpleUploadedFile("logo.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                                 content_type="image/svg+xml")
        fake = SimpleUploadedFile("logo.png", b"%PDF-1.4 not an image", content_type="image/png")
        for f, why in ((svg, "not a PNG, JPEG or WebP"), (fake, "not a PNG, JPEG or WebP"),
                       (image_file("GIF", name="logo.gif"), "must be a PNG, JPEG or WebP")):
            r = self.upload(f)
            self.assertEqual(r.status_code, 400, f.name)
            self.assertIn(why, r.json()["detail"])
        big = SimpleUploadedFile("big.png", b"\x89PNG" + b"0" * (3 * 1024 * 1024), content_type="image/png")
        r = self.upload(big)
        self.assertIn(r.status_code, (400, 413))                          # 2 MB logo limit / 5 MB image limit

    def test_replace_and_remove(self):
        first = self.upload(image_file("PNG")).json()["logo_version"]
        second = self.upload(image_file("WEBP")).json()["logo_version"]
        self.assertNotEqual(first, second)                                 # new ?v= so browsers refresh
        r = Client(HTTP_HOST=PLATFORM).delete(self.url(), HTTP_AUTHORIZATION=f"Bearer {self.platform_token()}")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["logo_version"])
        self.assertIsNone(self.college_info()["logo_version"])

    def test_switched_off_college_still_shows_its_logo(self):
        self.upload(image_file())
        with schema_context("public"):
            self.college.is_active = False
            self.college.save(update_fields=["is_active"])
        self.assertEqual(Client(HTTP_HOST=COLLEGE_HOST).get("/api/college/logo/").status_code, 200)

    def test_colleges_list_says_who_has_a_logo(self):
        self.upload(image_file())
        r = self.api("get", "/api/platform/colleges/", self.platform_token())
        row = next(c for c in r.json() if c["code"] == "test")
        self.assertIsNotNone(row["logo_version"])
