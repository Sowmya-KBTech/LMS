"""
WAVE 2 - SURVEYS.

A Survey has Questions. When someone answers:
  * a Participation row records THAT they answered (stops answering twice,
    gives the response rate),
  * a Response row holds WHAT they answered. On an anonymous survey the
    Response stores no respondent and no time, and no screen or API ever links
    answers to a person. (Someone with direct database access could still try
    to match rows by their order, so this is "anonymous in the app", not a
    cryptographic guarantee.)
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Survey(models.Model):

    class Audience(models.TextChoices):
        STUDENTS = "students", "Students"
        STAFF = "staff", "Teaching staff"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.STUDENTS)

    # who answers: blank = everyone in the audience
    department = models.ForeignKey("users.Department", on_delete=models.CASCADE, null=True, blank=True,
                                   related_name="surveys")
    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, null=True, blank=True,
                               related_name="surveys")
    year = models.PositiveSmallIntegerField(null=True, blank=True)          # 1..4, students only
    semester = models.PositiveSmallIntegerField(null=True, blank=True)      # students only

    anonymous = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)                      # last day to answer
    template = models.CharField(max_length=40, blank=True)                  # which template it came from
    # CO-PO PART C: a course exit survey belongs to one subject's class; only
    # the students enrolled in it answer (department/course/year don't apply)
    teaching_assignment = models.ForeignKey("courses.TeachingAssignment", on_delete=models.CASCADE, null=True,
                                            blank=True, related_name="exit_surveys")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   related_name="surveys_created")
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def is_accepting(self, today=None):
        """Open, and today is inside the dates."""
        today = today or timezone.localdate()
        return (self.status == self.Status.OPEN and self.start_date <= today
                and (self.end_date is None or today <= self.end_date))


class Question(models.Model):

    class Kind(models.TextChoices):
        RATING = "rating", "Rating 1-5"
        CHOICE = "choice", "One choice"
        MULTI = "multi", "Several choices"
        TEXT = "text", "Written answer"

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveSmallIntegerField(default=0)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.RATING)
    text = models.CharField(max_length=500)
    required = models.BooleanField(default=True)
    options = models.JSONField(default=list, blank=True)                    # for choice / multi
    # CO-PO PART C: the course outcome a course-exit question asks about
    outcome = models.ForeignKey("teachingplan.CourseOutcome", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="survey_questions")

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text[:60]


class Participation(models.Model):
    """That this person answered (never what they answered)."""
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="participations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["survey", "user"], name="one_answer_per_person")]


class Response(models.Model):
    """What was answered. respondent is empty on anonymous surveys."""
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="responses")
    respondent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name="+")


class Answer(models.Model):
    response = models.ForeignKey(Response, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    choices = models.JSONField(default=list, blank=True)
    text = models.TextField(blank=True)
