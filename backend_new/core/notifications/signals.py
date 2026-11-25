from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from core.notifications.cache import invalidate_unread
from core.notifications.models import Notification


# ---- Email for a new Notification ----
# EMAIL QUEUE FIX (Point 12, G4): emails are NO LONGER sent inside the request.
#
# Before: every new Notification opened its own Gmail connection here, while
# the user waited. An announcement to 500 students = 500 SMTP connections in
# one request. It also never set `emailed_at`, so the queue command would have
# sent every old notification again.
#
# Now (default, NOTIFICATION_EMAIL_MODE = "queue"): the Notification is saved
# with emailed_at = NULL, and `python manage.py send_notification_emails`
# (every 10 minutes by Celery Beat, for every college) sends the pending ones in
# batches over one connection, marks emailed_at, and retries failures 3 times.
#
# Fallback (NOTIFICATION_EMAIL_MODE = "immediate" in settings): send at once,
# as before, but mark emailed_at so the queue never sends it a second time.
def email_immediately():
    return getattr(settings, "NOTIFICATION_EMAIL_MODE", "queue") == "immediate"


def send_now(notification):
    """Fallback mode only: email one notification now and mark it emailed."""
    from core.notifications.emails import send_notification_email
    if send_notification_email(
        recipient=notification.recipient,
        title=notification.title,
        message=notification.message,
    ):
        Notification.objects.filter(pk=notification.pk).update(emailed_at=timezone.now())


@receiver(post_save, sender=Notification)
def email_on_notification(sender, instance, created, **kwargs):
    if created and email_immediately():
        send_now(instance)
    # queue mode (default): nothing here — send_notification_emails delivers it


# ---- Bell cache (Redis/Celery work, step 4) ----
# Any change to a notification (new, marked read, deleted) clears that user's
# cached unread list after the transaction commits. Bulk create/update skip
# these signals, so those places call invalidate_unread() themselves.
@receiver(post_save, sender=Notification)
def clear_bell_cache_on_save(sender, instance, **kwargs):
    invalidate_unread([instance.recipient_id])


@receiver(post_delete, sender=Notification)
def clear_bell_cache_on_delete(sender, instance, **kwargs):
    invalidate_unread([instance.recipient_id])
