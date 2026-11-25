"""
Single place for sending notification emails.
Nothing else in the codebase should call Django's email functions directly.
"""
from django.core.mail import EmailMessage, get_connection, send_mail
from django.conf import settings


def send_notification_email(recipient, title, message):
    """
    Send ONE notification email, immediately, on its own connection.
    Opening a connection per email is fine for a one-off and ruinous in a loop.
    """
    email_address = getattr(recipient, "email", "") or ""
    email_address = email_address.strip()

    if not email_address:
        return False

    try:
        send_mail(
            subject=title,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email_address],
            fail_silently=False,
        )
        return True
    except Exception as exc:
        print(f"[email] failed to send to {email_address}: {exc}")
        return False


def send_notification_batch(notifications):
    """
    Send many notifications over a SINGLE SMTP connection.
    Returns (sent_ids, skipped_ids, failed_ids).
    """
    sent, skipped, failed = [], [], []

    notifications = list(notifications)
    if not notifications:
        return sent, skipped, failed

    deliverable = []
    for n in notifications:
        address = (getattr(n.recipient, "email", "") or "").strip()
        if address:
            deliverable.append((n, address))
        else:
            skipped.append(n.id)

    if not deliverable:
        return sent, skipped, failed

    connection = None
    try:
        connection = get_connection(fail_silently=False)
        connection.open()
    except Exception as exc:
        print(f"[email] could not open a connection: {exc}")
        return sent, skipped, [n.id for n, _ in deliverable]

    try:
        for n, address in deliverable:
            try:
                EmailMessage(
                    subject=n.title,
                    body=n.message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[address],
                    connection=connection,
                ).send(fail_silently=False)
                sent.append(n.id)
            except Exception as exc:
                print(f"[email] failed to send to {address}: {exc}")
                failed.append(n.id)
    finally:
        try:
            connection.close()
        except Exception:
            pass

    return sent, skipped, failed
