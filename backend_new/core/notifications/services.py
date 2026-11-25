from core.notifications.models import Notification


def notify_parents(student, title, message, notif_type, ta=None, link=""):
    from core.users.models import ParentProfile
    for pp in ParentProfile.objects.filter(children=student):
        Notification.objects.create(
            recipient=pp.user, title=title,
            message=message, notification_type=notif_type,
            teaching_assignment=ta, link=link,
        )


def notify(recipients, title, message, notif_type="announcement", link="", ta=None):
    """
    FIX #11: one helper for leave / on-duty / exam notifications.
    recipients may contain None or duplicates; both are skipped.
    A failed notification must never break the action that triggered it.
    """
    try:
        seen = set()
        rows = []
        for r in recipients or []:
            if r is None or r.id in seen:
                continue
            seen.add(r.id)
            rows.append(Notification(
                recipient=r, title=title[:200], message=(message or "")[:400],
                notification_type=notif_type, link=link, teaching_assignment=ta,
            ))
        created = Notification.objects.bulk_create(rows)
        from core.notifications.cache import invalidate_unread
        invalidate_unread(seen)  # bulk_create skips signals: clear the bell cache
        # EMAIL QUEUE FIX (Point 12, G4): bulk_create skips the post_save
        # signal, so these rows used to get NO email at all. Default (queue):
        # they wait with emailed_at = NULL and send_notification_emails sends
        # them. Fallback "immediate" mode: send them now, like single rows.
        from core.notifications.signals import email_immediately, send_now
        if email_immediately():
            for n in created:
                send_now(n)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("notify failed: %s", title)