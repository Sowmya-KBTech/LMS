from decimal import Decimal

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

    
# ===================== FILE CLEANUP SIGNAL =====================
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

User = get_user_model()


class Fee(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partial'),
        ('paid', 'Paid'),
    ]
    student = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='fees',
        limit_choices_to={'role': 'student'}
    )
    term = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.username} - {self.term}"

    def recalculate(self):
        """
        Single source of truth for this fee's figures.

        paid_amount, status and paid_date are always DERIVED from the
        FeePayment rows - never incremented in place. Called from the signals
        below whenever a payment is created, changed or deleted, so a
        correction made in the Django admin refreshes the fee exactly the same
        way a payment through the API does.
        """
        was_paid = self.status == 'paid'   # FIX #11
        total = self.payments.aggregate(
            t=models.Sum('amount')
        )['t'] or Decimal('0')

        self.paid_amount = total

        if total >= self.amount:
            self.status = 'paid'
            last = self.payments.first()          # Meta.ordering: newest first
            self.paid_date = last.paid_on if last else None
        elif total > 0:
            self.status = 'partial'
            self.paid_date = None
        else:
            self.status = 'pending'
            self.paid_date = None

        self.save(update_fields=['paid_amount', 'status', 'paid_date'])

        # FIX #11: paying the attendance fine unlocks the hall ticket - say so
        if self.status == 'paid' and not was_paid and \
                str(self.term).startswith("Attendance Shortage Fine"):
            try:
                from core.notifications.services import notify
                notify([self.student], "Hall ticket unlocked",
                       f"Your attendance fine ({self.term}) is paid. "
                       f"You can now download your hall ticket.",
                       "exam", link="/results?tab=ht")
            except Exception:
                pass

    class Meta:
        db_table = 'courses_fee'  # table kept from the old 'courses' app


# ===================== FEE PAYMENT =====================
class FeePayment(models.Model):

    MODE_CHOICES = [
        ('cash', 'Cash'),
        ('upi', 'UPI'),
        ('card', 'Card'),
        ('cheque', 'Cheque'),
        ('dd', 'Demand Draft'),
        ('netbanking', 'Net banking'),
        ('online', 'Online (gateway)'),
    ]

    fee = models.ForeignKey(
        Fee, on_delete=models.CASCADE, related_name='payments'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    # How the money arrived. Defaults to cash because every payment recorded
    # before this field existed was taken at the counter.
    mode = models.CharField(max_length=12, choices=MODE_CHOICES, default='cash')

    # Issued once in save(), never reused. Blank only on rows created before
    # this field existed.
    receipt_no = models.CharField(max_length=30, blank=True, db_index=True)

    paid_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='fee_payments_made'
    )
    recorded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='fee_payments_recorded'
    )
    paid_on = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=100, blank=True)
    remarks = models.TextField(blank=True)
    gateway_payment_id = models.CharField(
        max_length=100, unique=True, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'courses_feepayment'  # table kept from the old 'courses' app
        ordering = ['-paid_on', '-id']

    def __str__(self):
        return f"{self.fee.student.username} - {self.amount} on {self.paid_on}"

    def save(self, *args, **kwargs):
        """
        Issue a receipt number on first save and never change it afterwards.
        Format: RCPT-<year>-<5 digits>, restarting each calendar year.

        The sequence is read from the highest existing number rather than a
        counter, so a deleted row does not shift every later receipt.
        """
        if not self.receipt_no:
            year = timezone.localdate().year
            prefix = f"RCPT-{year}-"
            last = (
                FeePayment.objects
                .filter(receipt_no__startswith=prefix)
                .order_by('-receipt_no')
                .values_list('receipt_no', flat=True)
                .first()
            )
            nxt = 1
            if last:
                try:
                    nxt = int(last.rsplit('-', 1)[1]) + 1
                except (IndexError, ValueError):
                    nxt = FeePayment.objects.filter(
                        receipt_no__startswith=prefix
                    ).count() + 1
            self.receipt_no = f"{prefix}{nxt:05d}"
        super().save(*args, **kwargs)


# ===================== FEE RECALCULATION SIGNALS =====================
# Fee.paid_amount / status / paid_date are derived values. These signals mean
# ANY change to a payment row refreshes them - through the API, the Django
# admin, a shell session or a future bulk import. There is no write path that
# can leave a fee disagreeing with its own payment history.

@receiver(post_save, sender=FeePayment)
def feepayment_saved(sender, instance, **kwargs):
    instance.fee.recalculate()


@receiver(post_delete, sender=FeePayment)
def feepayment_deleted(sender, instance, **kwargs):
    instance.fee.recalculate()


# ===================== PAYMENT TRANSACTION =====================
class PaymentTransaction(models.Model):
    """
    One ATTEMPT to pay a Fee online. An attempt log, not money received.
    Money received is still a FeePayment row. A FeePayment is created only
    when a transaction reaches 'success' after the server verifies
    Razorpay's signature.

    Fines and revaluation charges are Fee rows too, so this one FK covers
    every payable item in the system.
    """

    STATUS_CHOICES = [
        ('created', 'Created'),
        ('attempted', 'Attempted'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    fee = models.ForeignKey(
        Fee, on_delete=models.CASCADE, related_name='transactions'
    )
    initiated_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='payment_transactions'
    )

    # Rupees. Conversion to paise happens only at the API boundary.
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    provider = models.CharField(max_length=20, default='razorpay')
    gateway_order_id = models.CharField(max_length=100, unique=True)
    gateway_payment_id = models.CharField(
        max_length=100, blank=True, db_index=True
    )
    gateway_signature = models.CharField(max_length=200, blank=True)

    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='created'
    )
    failure_reason = models.TextField(blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    payment = models.OneToOneField(
        FeePayment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transaction'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'courses_paymenttransaction'  # table kept from the old 'courses' app
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f"{self.gateway_order_id} - {self.amount} ({self.status})"


# ===================== PHASE 3: RAZORPAY KEYS PER COLLEGE =====================
class PaymentSettings(models.Model):
    """
    THIS college's own Razorpay account.

    The fees app is a tenant app, so every college schema has its own copy of
    this table - ABC's keys live in ABC's schema, XYZ's in XYZ's. Fees paid at
    abc.kbtechcampus.in can only ever use ABC's keys, so the money reaches
    ABC's bank account.

    One row per college (id = 1). The Key ID is public (the checkout popup
    shows it); the two secrets are stored ENCRYPTED (modules/fees/crypto.py)
    and are never sent back by any API.
    """
    key_id = models.CharField(max_length=64, blank=True)
    key_secret_encrypted = models.TextField(blank=True)
    webhook_secret_encrypted = models.TextField(blank=True)

    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Payment settings'
        verbose_name_plural = 'Payment settings'

    def __str__(self):
        return f"Razorpay {self.mode or 'not set up'}"

    # ---------- the one row ----------
    @classmethod
    def current(cls):
        """This college's settings (an empty, unsaved row if never set)."""
        return cls.objects.filter(pk=1).first() or cls(pk=1)

    # ---------- secrets ----------
    def set_key_secret(self, plain):
        from modules.fees.crypto import encrypt
        self.key_secret_encrypted = encrypt(plain)

    def set_webhook_secret(self, plain):
        from modules.fees.crypto import encrypt
        self.webhook_secret_encrypted = encrypt(plain)

    @property
    def key_secret(self):
        from modules.fees.crypto import decrypt
        return decrypt(self.key_secret_encrypted)

    @property
    def webhook_secret(self):
        from modules.fees.crypto import decrypt
        return decrypt(self.webhook_secret_encrypted)

    # ---------- status ----------
    @property
    def is_configured(self):
        """Ready to take payments: a Key ID and a Key Secret are saved."""
        return bool(self.key_id and self.key_secret_encrypted)

    @property
    def has_webhook(self):
        return bool(self.webhook_secret_encrypted)

    @property
    def mode(self):
        """'test' or 'live', read from the Key ID itself (rzp_test_ / rzp_live_)."""
        if self.key_id.startswith('rzp_live_'):
            return 'live'
        if self.key_id.startswith('rzp_test_'):
            return 'test'
        return None
