from django.db.models.signals import post_save
from django.dispatch import receiver
from modules.learning.models import Assignment, QuizAttempt
from core.notifications.services import notify_parents


@receiver(post_save, sender=Assignment)
def on_assignment(sender, instance, created, **kwargs):
    if not created: return
    from core.academics.models import Enrollment
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
    # WAVE 3 PART 3: an online test still being written is not a result
    if getattr(instance, "status", "submitted") != "submitted": return
    # WAVE 3 PART 3b: written answers still to mark - parents hear when results are released
    if getattr(instance, "written_pending", False): return
    notify_parents(instance.student,
        "Quiz Result Published",
        f"Your child scored {instance.score} in "
        f"'{instance.quiz.title}'",
        'quiz', instance.quiz.teaching_assignment)
