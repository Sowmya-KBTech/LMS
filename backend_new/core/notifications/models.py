
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.academics.models import (
    TeachingAssignment,
)
    
# ===================== FILE CLEANUP SIGNAL =====================

User = get_user_model()


# ===================== NOTIFICATION =====================
class Notification(models.Model):

    NOTIFICATION_TYPES = [

        ('assignment', 'Assignment'),
        ('lecture', 'Lecture'),
        ('quiz', 'Quiz'),
        ('material', 'Study Material'),
        ('discussion', 'Discussion'),
        ('marks', 'Marks Published'),
        ('announcement', 'Announcement'),
         ('placement', 'Placement'),
        # FIX #23: say WHERE a notification came from, so a click opens the right page
        ('group', 'Class group'),
        ('mentoring', 'Mentoring'),
        ('teachingplan', 'Teaching plan'),
        ('chat', 'Message'),
        # FIX #11: staff leave, student on-duty, exam results / hall ticket
        ('leave', 'Staff leave'),
        ('od', 'On duty'),
        ('exam', 'Exam / results'),
    ]

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    # NEW FIELD
    teaching_assignment = models.ForeignKey(
        TeachingAssignment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications"
    )

    title = models.CharField(
        max_length=200
    )

    message = models.TextField()

    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        default='announcement'
    )
    is_read = models.BooleanField(
        default=False
    )

    # FIX #23b: the exact page to open, e.g. "/my-groups?group=12".
    # Blank for older notifications; the frontend then decides from the type.
    link = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(
        default=timezone.now
    )
     # ---- email delivery ----
        # Emails are sent by the send_notification_emails management command, not
        # in the request that created the row. Creating 60 fees used to mean 60
        # blocking SMTP round trips inside one HTTP request.
    emailed_at = models.DateTimeField(null=True, blank=True)
    email_attempts = models.PositiveSmallIntegerField(default=0)

    def __str__(self):

        return (
            f"{self.recipient} → "
            f"{self.title}"
        )

    class Meta:
        db_table = 'courses_notification'  # table kept from the old 'courses' app
