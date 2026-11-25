"""
WAVE 3 PART 1A - CBCS: regulations, course categories and credit requirements.

  Regulation         one set of rules (e.g. "R2021"): grade scale, pass rules,
                     degree class. ONE is the default.
  RegulationBatch    which admission batch (User.batch_year) follows which
                     regulation. A batch with no row follows the default.
  PassRule           marks split and pass marks, per subject type
                     (theory / practical / project).
  GradeBand          the grade scale. "pass" grades start at a total-mark %;
                     ONE "fail" grade (RA) is given when a pass rule is not met;
                     "arrear" grades (SA) and "excluded" grades (W) are given
                     by hand, never from marks.
  DegreeClass        first class with distinction / first class / ...
  CourseCategory     HSMC, BSC, ESC, PCC ... (one list for the college)
  CreditRequirement  credits a course needs in a category under a regulation.

Every number is a college SETTING (we do not know which university the client
follows); a template is offered to start from. The rules live in
core/academics/regulations.py.
"""
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

SUBJECT_KINDS = [
    ("theory", "Theory"),
    ("practical", "Practical"),
    ("project", "Project"),
]

GRADE_OUTCOMES = [
    ("pass", "Pass"),
    ("fail", "Arrear · write again"),            # given when a pass rule is not met (RA)
    ("arrear", "Arrear · given by hand"),        # e.g. SA - shortage of attendance
    ("excluded", "Not counted in CGPA"),         # e.g. W - withdrawn
]

ARREARS_IN_GPA = [
    ("exclude", "Left out until passed"),
    ("zero", "Counted with 0 points"),
]

REATTEMPT_INTERNAL = [
    ("keep", "Keep the first attempt's"),
    ("reenter", "Enter again"),
]


class Regulation(models.Model):
    name = models.CharField(max_length=30, unique=True)               # "R2021"
    description = models.CharField(max_length=200, blank=True, default="")
    is_default = models.BooleanField(default=False)
    arrears_in_gpa = models.CharField(max_length=10, choices=ARREARS_IN_GPA, default="exclude")
    reattempt_internal = models.CharField(max_length=10, choices=REATTEMPT_INTERNAL, default="keep")
    created_by = models.ForeignKey("users.User", null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "-name"]
        constraints = [
            models.UniqueConstraint(fields=["is_default"], condition=models.Q(is_default=True),
                                    name="one_default_regulation"),
        ]

    def __str__(self):
        return self.name


class RegulationBatch(models.Model):
    regulation = models.ForeignKey(Regulation, on_delete=models.CASCADE, related_name="batches")
    batch_year = models.PositiveSmallIntegerField(unique=True)        # admission year, e.g. 2021

    class Meta:
        ordering = ["batch_year"]

    def __str__(self):
        return f"{self.batch_year} -> {self.regulation}"


class PassRule(models.Model):
    regulation = models.ForeignKey(Regulation, on_delete=models.CASCADE, related_name="pass_rules")
    kind = models.CharField(max_length=10, choices=SUBJECT_KINDS)
    internal_max = models.PositiveSmallIntegerField(validators=[MaxValueValidator(200)])
    end_max = models.PositiveSmallIntegerField(validators=[MaxValueValidator(200)])
    min_end_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                      validators=[MinValueValidator(0), MaxValueValidator(100)])
    min_total_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                        validators=[MinValueValidator(0), MaxValueValidator(100)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["regulation", "kind"], name="one_pass_rule_per_kind")]


class GradeBand(models.Model):
    regulation = models.ForeignKey(Regulation, on_delete=models.CASCADE, related_name="grades")
    code = models.CharField(max_length=4)                              # "O", "A+", "RA"
    meaning = models.CharField(max_length=60, blank=True, default="")
    outcome = models.CharField(max_length=10, choices=GRADE_OUTCOMES, default="pass")
    # pass grades only: the grade applies from this total-mark percentage up to
    # the next pass grade's start (the top one up to 100). No gaps or overlaps.
    min_mark = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                   validators=[MinValueValidator(0), MaxValueValidator(100)])
    points = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True,
                                 validators=[MinValueValidator(0), MaxValueValidator(10)])
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["regulation", "code"], name="unique_grade_code")]


class DegreeClass(models.Model):
    regulation = models.ForeignKey(Regulation, on_delete=models.CASCADE, related_name="classes")
    name = models.CharField(max_length=60)
    min_cgpa = models.DecimalField(max_digits=4, decimal_places=2, default=0,
                                   validators=[MinValueValidator(0), MaxValueValidator(10)])
    first_attempt_only = models.BooleanField(default=False)            # every subject passed at the first try
    extra_years = models.PositiveSmallIntegerField(null=True, blank=True)   # within normal duration + N years
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]


class CourseCategory(models.Model):
    code = models.CharField(max_length=10, unique=True)               # "PCC"
    name = models.CharField(max_length=80)
    carries_credit = models.BooleanField(default=True)                # MC: pass needed, no credit
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["order", "code"]

    def __str__(self):
        return self.code


class CreditRequirement(models.Model):
    regulation = models.ForeignKey(Regulation, on_delete=models.CASCADE, related_name="requirements")
    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="credit_requirements")
    category = models.ForeignKey(CourseCategory, on_delete=models.CASCADE, related_name="requirements")
    credits = models.DecimalField(max_digits=5, decimal_places=1, default=0,
                                  validators=[MinValueValidator(0), MaxValueValidator(400)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["regulation", "course", "category"],
                                               name="one_requirement_per_category")]
