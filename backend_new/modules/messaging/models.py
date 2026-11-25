
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

    
# ===================== FILE CLEANUP SIGNAL =====================

User = get_user_model()


    
# ===================== PARENT MESSAGE =====================
class ParentMessage(models.Model):
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='sent_messages'
    )
    receiver = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='received_messages'
    )
    text = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    # Which relationship this message belongs to. Two people who hold two
    # roles (mentor AND tutor) get two separate threads, so a
    # mentoring conversation never surfaces on the tutor's page.
    CONTEXT_CHOICES = (
        ("mentor", "Mentor and mentee"),
        ("advisor", "Tutor and student"),
        ("parent", "Teacher and parent"),
        ("general", "Uncategorised"),
    )
    context = models.CharField(
        max_length=10, choices=CONTEXT_CHOICES, default="general", db_index=True
    )

    class Meta:
        db_table = 'courses_parentmessage'  # table kept from the old 'courses' app
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.username} → {self.receiver.username}"


    
# ===================== CONVERSATION MESSAGE =====================
class ConversationMessage(models.Model):
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='sent_convo_messages'
    )
    receiver = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='received_convo_messages'
    )
    text = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    # Files on a private thread. Same 10 MB ceiling as class group uploads.
    attachment = models.FileField(
        upload_to="private_messages/%Y/%m/", null=True, blank=True
    )
    attachment_name = models.CharField(max_length=200, blank=True)
    attachment_size = models.PositiveIntegerField(default=0)

    CONTEXT_CHOICES = (
        ("mentor", "Mentor and mentee"),
        ("advisor", "Tutor and student"),
        ("parent", "Teacher and parent"),
        ("general", "Uncategorised"),
    )
    context = models.CharField(
        max_length=10, choices=CONTEXT_CHOICES, default="general", db_index=True
    )

    class Meta:
        db_table = 'courses_conversationmessage'  # table kept from the old 'courses' app
        ordering = ['created_at']

    def save(self, *args, **kwargs):
        # keep the original filename and size — the stored path is mangled
        if self.attachment and not self.attachment_name:
            self.attachment_name = self.attachment.name.rsplit("/", 1)[-1]
        if self.attachment and not self.attachment_size:
            try:
                self.attachment_size = self.attachment.size
            except Exception:
                self.attachment_size = 0
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sender.username} -> {self.receiver.username}"
