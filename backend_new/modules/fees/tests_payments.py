"""
PHASE 3 TESTS - every college takes fees into ITS OWN Razorpay account.

The test runner puts every test inside the college "test" (address
"testserver"). These tests add a second college, "other" (other.localhost),
and check that each college's payments use only its own keys.

Razorpay itself is never called: razorpay.Client is replaced by a fake that
records which keys it was given.

Run:  python manage.py test modules.fees -v 2
"""
import hashlib
import hmac
import json
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django_tenants.utils import get_public_schema_name, schema_context

from core.tenants.models import College, Domain, PlatformAdmin
from modules.fees.models import Fee, FeePayment, PaymentSettings, PaymentTransaction

PASSWORD = "Strong@12345"
HOME = "testserver"
OTHER = "other.localhost"

HOME_KEYS = ("rzp_test_HomeKey12345", "home-secret-111", "home-webhook-111")
OTHER_KEYS = ("rzp_test_OtherKey6789", "other-secret-222", "other-webhook-222")


def fake_razorpay():
    """A stand-in for razorpay.Client that remembers the keys of every client made."""
    used = []

    def make_client(auth):
        used.append(auth)
        client = mock.MagicMock()
        client.order.create.side_effect = lambda data: {
            "id": f"order_{auth[0][-5:]}_{len(used)}",
            "amount": data["amount"], "currency": "INR"}
        return client

    return used, make_client


def save_keys(keys, by=None):
    ps = PaymentSettings.current()
    ps.key_id = keys[0]
    ps.set_key_secret(keys[1])
    ps.set_webhook_secret(keys[2])
    ps.updated_by = by
    ps.save()
    return ps


class PaymentTestBase(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.home = connection.tenant                      # the runner's "test" college
        connection.set_schema_to_public()
        cls.other = College.objects.create(schema_name="payother", name="Other College")
        Domain.objects.create(domain=OTHER, tenant=cls.other, is_primary=True)
        connection.set_tenant(cls.home)

    @classmethod
    def tearDownClass(cls):
        connection.set_tenant(cls.home)
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("principal", "", PASSWORD)
        self.student = User.objects.create_user("stu1", password=PASSWORD, role="student")
        self.teacher = User.objects.create_user("teach1", password=PASSWORD, role="teacher")
        self.academic = User.objects.create_user(
            "acad1", password=PASSWORD, role="admin", sub_role="academic_admin")
        self.accounts = User.objects.create_user(
            "acct1", password=PASSWORD, role="admin", sub_role="accounts_admin")
        self.fee = Fee.objects.create(
            student=self.student, term="Tuition", amount=50000, due_date=date(2026, 12, 31))

        with schema_context("payother"):
            other_student = User.objects.create_user("stu1", password=PASSWORD, role="student")
            self.other_fee_id = Fee.objects.create(
                student=other_student, term="Tuition", amount=40000,
                due_date=date(2026, 12, 31)).id

    def tearDown(self):
        connection.set_tenant(self.home)

    # ---------- helpers ----------
    def token(self, username, host=HOME):
        r = Client(HTTP_HOST=host).post(
            "/api/users/login/", {"username": username, "password": PASSWORD},
            content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["access"]

    def api(self, method, path, username=None, data=None, host=HOME, token=None):
        c = Client(HTTP_HOST=host)
        kwargs = {}
        if username or token:
            kwargs["HTTP_AUTHORIZATION"] = f"Bearer {token or self.token(username, host)}"
        if data is not None:
            kwargs.update(data=data, content_type="application/json")
        return getattr(c, method)(path, **kwargs)


# =====================================================================
#  1) EACH COLLEGE'S PAYMENTS USE ITS OWN KEYS
# =====================================================================
class OwnKeysTests(PaymentTestBase):

    def test_no_keys_means_no_online_payment(self):
        r = self.api("post", f"/api/fees/{self.fee.id}/initiate-payment/", "stu1", {})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "payments_not_configured")
        self.assertIn("isn't set up", r.json()["detail"])
        self.assertFalse(PaymentTransaction.objects.exists())

    def test_payment_opens_in_this_colleges_account(self):
        save_keys(HOME_KEYS)
        used, make_client = fake_razorpay()
        with mock.patch("modules.fees.payments.razorpay.Client", side_effect=make_client):
            r = self.api("post", f"/api/fees/{self.fee.id}/initiate-payment/", "stu1", {})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(used, [HOME_KEYS[:2]])
        self.assertEqual(r.json()["key_id"], HOME_KEYS[0])
        self.assertNotIn(HOME_KEYS[1], r.content.decode())     # the secret never leaves

    def test_two_colleges_never_share_keys(self):
        save_keys(HOME_KEYS)
        with schema_context("payother"):
            save_keys(OTHER_KEYS)

        used, make_client = fake_razorpay()
        with mock.patch("modules.fees.payments.razorpay.Client", side_effect=make_client):
            a = self.api("post", f"/api/fees/{self.fee.id}/initiate-payment/", "stu1", {})
            b = self.api("post", f"/api/fees/{self.other_fee_id}/initiate-payment/", "stu1", {},
                         host=OTHER)
        self.assertEqual(a.status_code, 200, a.content)
        self.assertEqual(b.status_code, 200, b.content)
        self.assertEqual(used, [HOME_KEYS[:2], OTHER_KEYS[:2]])
        self.assertEqual(a.json()["key_id"], HOME_KEYS[0])
        self.assertEqual(b.json()["key_id"], OTHER_KEYS[0])

    def test_one_college_with_keys_does_not_help_another_without(self):
        save_keys(HOME_KEYS)
        r = self.api("post", f"/api/fees/{self.other_fee_id}/initiate-payment/", "stu1", {},
                     host=OTHER)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "payments_not_configured")

    def test_gateway_failure_is_explained(self):
        save_keys(HOME_KEYS)

        def broken(auth):
            client = mock.MagicMock()
            client.order.create.side_effect = ConnectionError("down")
            return client

        with mock.patch("modules.fees.payments.razorpay.Client", side_effect=broken):
            r = self.api("post", f"/api/fees/{self.fee.id}/initiate-payment/", "stu1", {})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["code"], "gateway_error")


# =====================================================================
#  2) CONFIRMING A PAYMENT USES THIS COLLEGE'S SECRETS
# =====================================================================
class VerifyAndWebhookTests(PaymentTestBase):

    def start_payment(self):
        save_keys(HOME_KEYS)
        used, make_client = fake_razorpay()
        with mock.patch("modules.fees.payments.razorpay.Client", side_effect=make_client):
            r = self.api("post", f"/api/fees/{self.fee.id}/initiate-payment/", "stu1", {})
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["order_id"]

    @staticmethod
    def sign(secret, message):
        return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()

    def test_signature_made_with_this_colleges_secret_is_accepted(self):
        order_id = self.start_payment()
        sig = self.sign(HOME_KEYS[1], f"{order_id}|pay_1".encode())
        r = self.api("post", "/api/payments/verify/", "stu1", {
            "razorpay_order_id": order_id, "razorpay_payment_id": "pay_1",
            "razorpay_signature": sig})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(FeePayment.objects.filter(gateway_payment_id="pay_1").count(), 1)

    def test_signature_made_with_another_colleges_secret_is_refused(self):
        order_id = self.start_payment()
        sig = self.sign(OTHER_KEYS[1], f"{order_id}|pay_2".encode())
        r = self.api("post", "/api/payments/verify/", "stu1", {
            "razorpay_order_id": order_id, "razorpay_payment_id": "pay_2",
            "razorpay_signature": sig})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(FeePayment.objects.exists())

    def webhook(self, secret, order_id, payment_id):
        body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
            "id": payment_id, "order_id": order_id}}}}).encode()
        return Client(HTTP_HOST=HOME).post(
            "/api/payments/webhook/razorpay/", data=body, content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=self.sign(secret, body))

    def test_webhook_checked_with_this_colleges_webhook_secret(self):
        order_id = self.start_payment()
        self.assertEqual(self.webhook(OTHER_KEYS[2], order_id, "pay_3").status_code, 400)
        self.assertEqual(self.webhook(HOME_KEYS[2], order_id, "pay_3").status_code, 200)
        self.assertEqual(FeePayment.objects.filter(gateway_payment_id="pay_3").count(), 1)

    def test_webhook_refused_when_no_webhook_secret_is_saved(self):
        order_id = self.start_payment()
        ps = PaymentSettings.current()
        ps.webhook_secret_encrypted = ""
        ps.save()
        self.assertEqual(self.webhook(HOME_KEYS[2], order_id, "pay_4").status_code, 400)


# =====================================================================
#  3) THE PAYMENT SETTINGS SCREEN
# =====================================================================
class PaymentSettingsApiTests(PaymentTestBase):
    URL = "/api/payments/settings/"

    def test_secrets_are_stored_encrypted(self):
        r = self.api("put", self.URL, "principal", {
            "key_id": HOME_KEYS[0], "key_secret": HOME_KEYS[1], "webhook_secret": HOME_KEYS[2]})
        self.assertEqual(r.status_code, 200, r.content)
        ps = PaymentSettings.objects.get()
        self.assertNotIn(HOME_KEYS[1], ps.key_secret_encrypted)
        self.assertNotIn(HOME_KEYS[2], ps.webhook_secret_encrypted)
        self.assertEqual(ps.key_secret, HOME_KEYS[1])
        self.assertEqual(ps.webhook_secret, HOME_KEYS[2])
        self.assertEqual(ps.updated_by, self.admin)

    def test_settings_never_return_the_secrets(self):
        save_keys(HOME_KEYS)
        r = self.api("get", self.URL, "principal")
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertNotIn(HOME_KEYS[1], body)
        self.assertNotIn(HOME_KEYS[2], body)
        data = r.json()
        self.assertTrue(data["configured"])
        self.assertEqual(data["mode"], "test")
        self.assertTrue(data["has_key_secret"])
        self.assertTrue(data["has_webhook_secret"])
        self.assertEqual(data["webhook_url"], "http://testserver/api/payments/webhook/razorpay/")

    def test_only_college_admin_or_accounts_admin_can_manage(self):
        for username in ("stu1", "teach1", "acad1"):
            self.assertEqual(self.api("get", self.URL, username).status_code, 403, username)
            self.assertEqual(self.api("put", self.URL, username, {
                "key_id": HOME_KEYS[0], "key_secret": "x"}).status_code, 403, username)
        self.assertEqual(self.api("get", self.URL, "acct1").status_code, 200)
        self.assertFalse(PaymentSettings.objects.exists())

    def test_bad_key_id_is_refused(self):
        r = self.api("put", self.URL, "principal", {"key_id": "not-a-key", "key_secret": "s"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("rzp_test_", r.json()["detail"])

    def test_blank_secret_keeps_the_saved_one(self):
        save_keys(HOME_KEYS)
        r = self.api("put", self.URL, "principal", {"key_id": HOME_KEYS[0], "key_secret": ""})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(PaymentSettings.current().key_secret, HOME_KEYS[1])
        self.assertEqual(PaymentSettings.current().webhook_secret, HOME_KEYS[2])

    def test_new_key_id_needs_its_own_secret(self):
        save_keys(HOME_KEYS)
        r = self.api("put", self.URL, "principal", {"key_id": "rzp_live_NewKey123456", "key_secret": ""})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(PaymentSettings.current().key_id, HOME_KEYS[0])

    def test_remove_keys_switches_online_payment_off(self):
        save_keys(HOME_KEYS)
        r = self.api("delete", self.URL, "principal")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["configured"])
        r = self.api("post", f"/api/fees/{self.fee.id}/initiate-payment/", "stu1", {})
        self.assertEqual(r.json()["code"], "payments_not_configured")

    def test_each_college_admin_sees_only_their_own_settings(self):
        save_keys(HOME_KEYS)
        with schema_context("payother"):
            get_user_model().objects.create_superuser("principal", "", PASSWORD)
        r = self.api("get", self.URL, "principal", host=OTHER)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["configured"])
        self.assertEqual(r.json()["key_id"], "")

    def test_test_connection_uses_the_keys_given(self):
        used = []

        def ok_client(auth):
            used.append(auth)
            return mock.MagicMock()

        with mock.patch("modules.fees.payments.razorpay.Client", side_effect=ok_client):
            r = self.api("post", self.URL + "test/", "principal",
                         {"key_id": HOME_KEYS[0], "key_secret": HOME_KEYS[1]})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["ok"])
        self.assertEqual(used, [HOME_KEYS[:2]])

    def test_test_connection_reports_rejected_keys(self):
        import razorpay

        def bad_client(auth):
            client = mock.MagicMock()
            client.order.all.side_effect = razorpay.errors.BadRequestError("Authentication failed")
            return client

        with mock.patch("modules.fees.payments.razorpay.Client", side_effect=bad_client):
            r = self.api("post", self.URL + "test/", "principal",
                         {"key_id": HOME_KEYS[0], "key_secret": "wrong"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.json()["ok"])
        self.assertIn("rejected", r.json()["detail"])

    def test_status_tells_the_pay_screen_whether_online_payment_works(self):
        r = self.api("get", "/api/payments/status/", "stu1")
        self.assertEqual(r.json(), {"online_payments": False, "mode": None})
        save_keys(HOME_KEYS)
        r = self.api("get", "/api/payments/status/", "stu1")
        self.assertEqual(r.json(), {"online_payments": True, "mode": "test"})

    def test_platform_sees_status_only_never_keys(self):
        save_keys(HOME_KEYS)
        connection.set_schema_to_public()
        public = College.objects.get(schema_name=get_public_schema_name())
        Domain.objects.get_or_create(domain="localhost", defaults={"tenant": public})
        kb = PlatformAdmin(username="kbadmin")
        kb.set_password(PASSWORD)
        kb.save()
        connection.set_tenant(self.home)

        c = Client(HTTP_HOST="localhost")
        tok = c.post("/api/platform/login/", {"username": "kbadmin", "password": PASSWORD},
                     content_type="application/json").json()["access"]
        r = c.get("/api/platform/colleges/", HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.content.decode()
        for secret in HOME_KEYS:
            self.assertNotIn(secret, body)
        by_code = {c["code"]: c for c in r.json()}
        self.assertEqual(by_code["test"]["online_payments"],
                         {"configured": True, "mode": "test", "webhook": True})
        self.assertEqual(by_code["payother"]["online_payments"]["configured"], False)


# =====================================================================
#  4) ENCRYPTION
# =====================================================================
class EncryptionTests(TestCase):

    def test_round_trip_and_blank(self):
        from modules.fees.crypto import decrypt, encrypt
        token = encrypt("abc-secret")
        self.assertNotEqual(token, "abc-secret")
        self.assertEqual(decrypt(token), "abc-secret")
        self.assertEqual(encrypt(""), "")
        self.assertEqual(decrypt(""), "")

    def test_a_different_server_key_cannot_read_it(self):
        from modules.fees.crypto import SecretUnreadable, decrypt, encrypt
        token = encrypt("abc-secret")
        with self.settings(PAYMENT_ENCRYPTION_KEY="x" * 43 + "="):
            with self.assertRaises(SecretUnreadable):
                decrypt(token)

    def test_unreadable_secret_means_not_configured_not_a_crash(self):
        ps = PaymentSettings.current()
        ps.key_id = HOME_KEYS[0]
        ps.key_secret_encrypted = "garbage-not-a-token"
        ps.save()
        from modules.fees.payments import PaymentsNotConfigured, college_keys
        with self.assertRaises(PaymentsNotConfigured):
            college_keys()
