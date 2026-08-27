# backend/classgroups/models.py
from django.conf import settings
from django.db import models


ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}


def group_upload_path(instance, filename):
    gid = getattr(instance, "group_id", None) or "misc"
    return f"class_groups/{gid}/{filename}"


# ================= GROUP =================
class ClassGroup(models.Model):
    """
    A conversation with a defined audience. Two kinds:

      CLASS   — the class advisor talks to everyone in a Course + Year.
                Derived from courses.YearTutor.
      SUBJECT — a subject teacher talks to the students enrolled in one
                subject for one class. Derived from courses.TeachingAssignment
                and courses.Enrollment.

    Membership is never stored. It is a query, so moving a student or changing
    the advisor updates the group with no extra step and nothing to keep in sync.

    This row exists only to hang settings and messages on. It is created on
    demand the first time someone opens the group.
    """

    CLASS = "class"
    SUBJECT = "subject"
    KIND_CHOICES = ((CLASS, "Class group"), (SUBJECT, "Subject group"))

    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default=CLASS)

    # class group -> course + year.  subject group -> teaching_assignment.
    course = models.ForeignKey(
        "courses.Course", on_delete=models.CASCADE,
        related_name="class_groups", null=True, blank=True,
    )
    year = models.ForeignKey(
        "courses.Year", on_delete=models.CASCADE,
        related_name="class_groups", null=True, blank=True,
    )
    teaching_assignment = models.ForeignKey(
        "courses.TeachingAssignment", on_delete=models.CASCADE,
        related_name="subject_groups", null=True, blank=True,
    )

    academic_year = models.CharField(max_length=9)          # "2026-2027"

    # ---------- settings the owning teacher controls ----------
    announcement_only = models.BooleanField(
        default=False,
        help_text="On: only the teacher can post. Students read but cannot reply.",
    )
    students_can_message = models.BooleanField(default=True)
    # On by default: students share notes and photos like staff do. The teacher
    # can switch it off for a group where it turns into assignment submissions
    # or worse — a permission you cannot revoke is not worth the simplicity.
    students_can_upload = models.BooleanField(default=True)

    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "course__name", "year__year_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "year", "academic_year"],
                condition=models.Q(kind="class"),
                name="one_class_group_per_class_per_year",
            ),
            models.UniqueConstraint(
                fields=["teaching_assignment", "academic_year"],
                condition=models.Q(kind="subject"),
                name="one_subject_group_per_assignment_per_year",
            ),
        ]

    def __str__(self):
        return self.display_name

    # ---------- naming, built from real data ----------
    @property
    def _year_number(self):
        if self.kind == self.CLASS:
            return self.year.year_number if self.year_id else None
        return self.teaching_assignment.year.year_number

    @property
    def _course(self):
        if self.kind == self.CLASS:
            return self.course
        return self.teaching_assignment.course

    @property
    def display_name(self):
        yn = self._year_number
        base = f"{ROMAN.get(yn, yn)} {self._course.name}"
        if self.kind == self.SUBJECT:
            return f"{base} \u00b7 {self.teaching_assignment.subject.name}"
        return base

    @property
    def subject_name(self):
        return self.teaching_assignment.subject.name if self.kind == self.SUBJECT else ""

    # ---------- audience, derived not stored ----------
    def students(self):
        """
        Class group  -> everyone in the course and year.
        Subject group-> only students with an Enrollment row.

        There is deliberately NO fallback from Enrollment to course+year. A
        missing enrolment must never turn into a message sent to the whole
        year; see has_audience() and the block in the view.
        """
        from users.models import User

        if self.kind == self.CLASS:
            return User.objects.filter(
                role="student", is_active=True,
                course=self.course, year=self.year.year_number,
            ).select_related("department", "course")

        return User.objects.filter(
            role="student", is_active=True,
            enrollment__teaching_assignment=self.teaching_assignment,
        ).distinct().select_related("department", "course")

    def has_audience(self):
        return self.students().exists()

    def owner(self):
        """The teacher this group belongs to."""
        if self.kind == self.SUBJECT:
            return self.teaching_assignment.teacher

        from courses.models import YearTutor
        link = (
            YearTutor.objects.filter(course=self.course, year=self.year)
            .select_related("teacher").first()
        )
        return link.teacher if link else None

    def can_post(self, user):
        if user == self.owner():
            return True
        if self.announcement_only or not self.students_can_message:
            return False
        return self.students().filter(id=user.id).exists()

    # ---------- creation on demand ----------
    @classmethod
    def for_class(cls, course, year, academic_year):
        obj, _ = cls.objects.get_or_create(
            kind=cls.CLASS, course=course, year=year, academic_year=academic_year
        )
        return obj

    @classmethod
    def for_assignment(cls, assignment, academic_year):
        obj, _ = cls.objects.get_or_create(
            kind=cls.SUBJECT, teaching_assignment=assignment,
            academic_year=academic_year,
        )
        return obj


# ================= MESSAGE =================
class ClassMessage(models.Model):
    """
    One table for the whole conversation.

    An announcement is a message the teacher marked important; a file is an
    attachment on a message. Shared Files is a filtered view of this table,
    not a separate store. That is why there is no ClassAnnouncement and no
    ClassFile model.
    """

    TEXT = "text"
    ANNOUNCEMENT = "announcement"
    TYPE_CHOICES = ((TEXT, "Message"), (ANNOUNCEMENT, "Announcement"))

    group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="class_messages"
    )

    message_type = models.CharField(max_length=14, choices=TYPE_CHOICES, default=TEXT)
    title = models.CharField(max_length=200, blank=True)      # announcements only
    text = models.TextField(blank=True)
    attachment = models.FileField(upload_to=group_upload_path, null=True, blank=True)
    attachment_name = models.CharField(max_length=200, blank=True)
    attachment_size = models.PositiveIntegerField(default=0)

    is_pinned = models.BooleanField(default=False)

    # soft delete: a class conversation is a record. The teacher can take a
    # message down, nobody can erase that it existed.
    is_deleted = models.BooleanField(default=False)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["group", "created_at"]),
            models.Index(fields=["group", "message_type"]),
        ]

    def save(self, *args, **kwargs):
        if self.attachment and not self.attachment_name:
            self.attachment_name = self.attachment.name.rsplit("/", 1)[-1]
        if self.attachment and not self.attachment_size:
            try:
                self.attachment_size = self.attachment.size
            except Exception:
                self.attachment_size = 0
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sender} in {self.group}"


# ================= READ STATE =================
class ClassMessageRead(models.Model):
    """Last message each person has seen in a group, for the unread badge."""

    group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="read_marks"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="class_read_marks"
    )
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "user"], name="one_read_mark_per_user")
        ]