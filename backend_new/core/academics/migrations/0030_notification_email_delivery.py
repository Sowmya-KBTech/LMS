from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0029_feepayment_mode_feepayment_receipt_no"),
    ]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="emailed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="email_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        # Everything that already exists has either been emailed or is old
        # enough not to matter. Without this the first command run would email
        # every historical notification at once.
        migrations.RunSQL(
            "UPDATE courses_notification SET emailed_at = NOW() WHERE emailed_at IS NULL;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]