from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Assignment, QuizAttempt, Notification, Fee

def notify_parents(student, title, message, notif_type, ta=None):
    from users.models import ParentProfile
    for pp in ParentProfile.objects.filter(children=student):
        Notification.objects.create(
            recipient=pp.user, title=title,
            message=message, notification_type=notif_type,
            teaching_assignment=ta
        )

@receiver(post_save, sender=Assignment)
def on_assignment(sender, instance, created, **kwargs):
    if not created: return
    from .models import Enrollment
    for e in Enrollment.objects.filter(
            teaching_assignment=instance.teaching_assignment):
        due_text = (
            instance.due_date.strftime("%d %b %Y, %I:%M %p")
            if instance.due_date else "No due date"
        )
        notify_parents(e.student,
            "New Assignment for your child",
            f"'{instance.title}' posted in "
            f"{instance.teaching_assignment.subject.name}. "
            f"Due: {due_text}",
            'assignment', instance.teaching_assignment)

@receiver(post_save, sender=QuizAttempt)
def on_quiz(sender, instance, **kwargs):
    if instance.score is None: return
    notify_parents(instance.student,
        "Quiz Result Published",
        f"Your child scored {instance.score} in "
        f"'{instance.quiz.title}'",
        'quiz', instance.quiz.teaching_assignment)

@receiver(post_save, sender=Fee)
def on_fee(sender, instance, created, **kwargs):
    if not created: return
    notify_parents(instance.student,
        "Fee Payment Due",
        f"{instance.term}: ₹{instance.amount} due by {instance.due_date}",
        'announcement')