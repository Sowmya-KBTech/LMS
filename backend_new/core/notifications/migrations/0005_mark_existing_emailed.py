# EMAIL QUEUE FIX (Point 12, G4)
# Until now every notification was emailed at once by a signal, but emailed_at
# was never set. Now the send_notification_emails queue sends every row with
# emailed_at = NULL. Mark all EXISTING notifications as already emailed, so
# the first queue run does not send the whole history again.
from django.db import migrations
from django.db.models import F


def mark_existing_emailed(apps, schema_editor):
    Notification = apps.get_model("notifications", "Notification")
    Notification.objects.filter(emailed_at__isnull=True).update(emailed_at=F("created_at"))


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0004_leave_od_exam_types"),
    ]

    operations = [
        migrations.RunPython(mark_existing_emailed, migrations.RunPython.noop),
    ]
