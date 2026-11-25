from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


# ===================== CALENDAR EVENT =====================
class CalendarEvent(models.Model):
    """
    A calendar entry created by admin (or synced from Google). Can be a
    holiday, event, or exam marker, targeted at an audience and optionally
    a specific year.
    """

    TYPE_CHOICES = [
        ('holiday', 'Holiday / Leave'),
        ('exam', 'Exam'),
        ('event', 'Event'),
    ]

    AUDIENCE_CHOICES = [
        ('everyone', 'Everyone'),
        ('teachers', 'Teachers'),
        ('students', 'Students'),
        ('parents', 'Parents'),
    ]

    # Where this entry came from. 'manual' = admin typed it in;
    # 'google' = synced from the Google holiday calendar.
    # Lets us re-sync Google holidays without touching manual entries.
    SOURCE_CHOICES = [
        ('manual', 'Manual'),
        ('google', 'Google'),
    ]

    title = models.CharField(max_length=200)
    event_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='event')
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default='everyone')
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='manual')
    year_number = models.IntegerField(null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='calendar_events'
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['start_date']

    def __str__(self):
        return f"{self.title} ({self.start_date})"


# ===================== ANNOUNCEMENT =====================
class Announcement(models.Model):
    AUDIENCE_CHOICES = (
        ('everyone', 'Everyone'),
        ('students', 'Students'),
        ('teachers', 'Teachers'),
        ('parents', 'Parents'),
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    audience = models.CharField(
        max_length=20,
        choices=AUDIENCE_CHOICES,
        default='everyone'
    )
    posted_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title