# backend/teachingplan/serializers.py
from datetime import date
from django.apps import apps
from rest_framework import serializers

from .models import TeachingPlan, PlanUnit, SUBJECT_MODEL, CourseOutcome, MAX_OUTCOMES


def _initials(name: str) -> str:
    parts = (name or "").split()
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _teacher_name(user) -> str:
    full = (user.get_full_name() or "").strip() if hasattr(user, "get_full_name") else ""
    return full or getattr(user, "username", "Unknown")


def _fmt_date(d):
    # "Jul 16" style; trims the leading zero off the day.
    if not d:
        return ""
    return f"{d.strftime('%b')} {d.day}"


def year_label(year):
    """A human class label from a Year row: 'B.E EEE - Year 1' style.

    MUST stay byte-identical to teachingplan/views.year_label(). The student view
    matches TeachingPlan.class_section against labels built by that function, so
    any drift between the two silently hides every plan from students.
    """
    if not year:
        return ""
    try:
        return f"{year.course.name} - Year {year.year_number}"
    except Exception:
        return str(year)


def class_labels_for(teacher, subject):
    """Every class label this teacher actually teaches this subject to.

    The class is a property of the TeachingAssignment, not something the teacher
    picks. Returns [] if there is no assignment (which means they shouldn't be
    writing a plan for this subject at all).
    """
    try:
        TA = apps.get_model("courses", "TeachingAssignment")
        assignments = (TA.objects
                       .filter(teacher=teacher, subject=subject)
                       .select_related("year", "year__course"))
        return [lbl for lbl in (year_label(a.year) for a in assignments) if lbl]
    except Exception:
        return []


# ---------- units ----------
class PlanUnitSerializer(serializers.ModelSerializer):
    # 'due' is what the frontend reads/writes; it maps to complete_by.
    due = serializers.DateField(source="complete_by", required=False, allow_null=True)
    # COURSE PLAN: readable labels for the HOD / student views (values stay codes)
    mode_label = serializers.CharField(source="get_mode_display", read_only=True)
    method_label = serializers.CharField(source="get_method_display", read_only=True)
    class_activity_label = serializers.CharField(source="get_class_activity_display", read_only=True)
    beyond_activity_label = serializers.CharField(source="get_beyond_activity_display", read_only=True)
    # COURSE PLAN (Part B): the course outcomes this session teaches (ids in, codes out)
    outcomes = serializers.PrimaryKeyRelatedField(many=True, required=False,
                                                  queryset=CourseOutcome.objects.all())
    outcome_codes = serializers.SerializerMethodField()

    def get_outcome_codes(self, obj):
        return [o.code for o in obj.outcomes.all()]

    class Meta:
        model = PlanUnit
        # period_no MUST be listed here. DRF silently discards any field that is not
        # declared — no error, no warning — so leaving it out means the frontend keeps
        # sending the period and the serializer keeps throwing it away.
        fields = ["id", "topic", "hours", "due", "period_no", "sequence_no",
                  "is_completed", "actual_completed_date",
                  # COURSE PLAN (upgrade)
                  "unit_no", "notes", "mode", "method", "class_activity", "beyond_activity",
                  "mode_label", "method_label", "class_activity_label", "beyond_activity_label",
                  # COURSE PLAN (Part B)
                  "outcomes", "outcome_codes"]


# ---------- create / edit a plan (teacher) ----------
class TeachingPlanWriteSerializer(serializers.ModelSerializer):
    units = PlanUnitSerializer(many=True)
    # Frontend sends the subject's primary key as `subject`.
    subject = serializers.PrimaryKeyRelatedField(
        queryset=apps.get_model(SUBJECT_MODEL).objects.all()
    )
    # The client may send this, but it is NOT trusted — see validate() below.
    class_section = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = TeachingPlan
        fields = ["id", "subject", "class_section", "semester", "allotted_hours", "status", "units"]

    def validate_status(self, value):
        # A teacher can only save as draft or submit for review here.
        if value not in ("draft", "submitted"):
            raise serializers.ValidationError("Status must be 'draft' or 'submitted'.")
        return value

    def validate(self, attrs):
        """Overwrite class_section with the authoritative value from the timetable.

        Previously this came straight from a dropdown that had no link to the
        selected subject, so a teacher who taught two classes could silently save
        a plan against the wrong one — and the student view, which matches on this
        exact string, would then never show it to anyone.
        """
        request = self.context.get("request")
        teacher = getattr(request, "user", None)
        subject = attrs.get("subject")

        # COURSE PLAN: a plan sent to the HOD must be complete enough to review.
        # Sessions without a topic are "not yet planned" and are not checked.
        if attrs.get("status") == "submitted":
            planned = [u for u in attrs.get("units", []) if (u.get("topic") or "").strip()]
            if not planned:
                raise serializers.ValidationError({"units": "Plan at least one session before sending it to the HOD."})
            for u in planned:
                missing = [label for key, label in (("unit_no", "a unit"), ("mode", "a teaching mode"))
                           if not u.get(key)]
                if missing:
                    when = u.get("complete_by")
                    where = f"The session on {when:%d-%m-%Y}" if when else f"The session \u201c{u['topic'][:40]}\u201d"
                    raise serializers.ValidationError(
                        {"units": f"{where} needs {' and '.join(missing)}."})

        # COURSE PLAN (Part B): a session may only point at this subject's outcomes
        if subject is not None:
            for u in attrs.get("units", []):
                if any(o.subject_id != subject.id for o in u.get("outcomes", [])):
                    raise serializers.ValidationError(
                        {"units": "A session is linked to a course outcome of another subject."})

        if teacher is None or subject is None:
            return attrs

        valid = class_labels_for(teacher, subject)
        if not valid:
            raise serializers.ValidationError({
                "subject": "You are not assigned to teach this subject to any class."
            })

        sent = (attrs.get("class_section") or "").strip()
        if sent in valid:
            attrs["class_section"] = sent      # teacher teaches it to >1 class, and picked a real one
        else:
            attrs["class_section"] = valid[0]  # ignore whatever the client sent

        return attrs

    def create(self, validated_data):
        units_data = validated_data.pop("units", [])
        request = self.context.get("request")

        from django.utils import timezone
        teacher = request.user
        department = getattr(teacher, "department", None)
        submitted_at = timezone.now() if validated_data.get("status") == "submitted" else None

        # FIX #36: the semester comes from the subject itself, never from the
        # dropdown (which defaulted to the teacher's FIRST semester, e.g. a
        # Semester 1 lab saved as "Semester 7").
        subj = validated_data["subject"]
        if getattr(subj, "semester", None):
            validated_data["semester"] = f"Semester {subj.semester}"

        # If a plan already exists for this teacher+subject+class+semester, update it
        # instead of creating a duplicate (which would violate unique_together).
        plan, _created = TeachingPlan.objects.update_or_create(
            teacher=teacher,
            subject=validated_data["subject"],
            class_section=validated_data["class_section"],
            semester=validated_data["semester"],
            defaults={
                "department": department,
                "allotted_hours": validated_data.get("allotted_hours", 0),
                "status": validated_data.get("status", "draft"),
                "submitted_at": submitted_at,
            },
        )

        # Replace the units with the ones just submitted
        plan.units.all().delete()
        for i, u in enumerate(units_data, start=1):
            unit = PlanUnit.objects.create(
                plan=plan,
                topic=u.get("topic", ""),
                hours=u.get("hours", 0),
                complete_by=u.get("complete_by"),
                # (complete_by, period_no) identifies the class hour. Without period_no
                # a subject that meets twice on one date has two indistinguishable rows.
                period_no=u.get("period_no"),
                sequence_no=u.get("sequence_no", i),
                # COURSE PLAN (upgrade)
                unit_no=u.get("unit_no"),
                notes=u.get("notes", ""),
                mode=u.get("mode", ""),
                method=u.get("method", ""),
                class_activity=u.get("class_activity", ""),
                beyond_activity=u.get("beyond_activity", ""),
            )
            if u.get("outcomes"):
                unit.outcomes.set(u["outcomes"])      # COURSE PLAN (Part B)
        return plan


# ---------- read a plan / department list (HOD) ----------
class TeachingPlanReadSerializer(serializers.ModelSerializer):
    code = serializers.SerializerMethodField()
    subject = serializers.SerializerMethodField()
    teacher = serializers.SerializerMethodField()
    initials = serializers.SerializerMethodField()
    cls = serializers.CharField(source="class_section")
    sem = serializers.CharField(source="semester")
    allotted = serializers.IntegerField(source="allotted_hours")
    status = serializers.SerializerMethodField()       # display status for the UI
    done = serializers.IntegerField(source="done_units")
    total = serializers.IntegerField(source="total_units")
    units = PlanUnitSerializer(many=True, read_only=True)

    class Meta:
        model = TeachingPlan
        fields = ["id", "code", "subject", "teacher", "initials", "cls", "sem",
                  "allotted", "status", "done", "total", "hod_comment", "units"]

    def get_code(self, obj):
        return getattr(obj.subject, "code", "") or ""

    def get_subject(self, obj):
        return getattr(obj.subject, "name", str(obj.subject))

    def get_teacher(self, obj):
        return _teacher_name(obj.teacher)

    def get_initials(self, obj):
        return _initials(_teacher_name(obj.teacher))

    def get_status(self, obj):
        # Map the stored status onto the strings the frontend expects.
        if obj.status == "submitted":
            return "pending"
        if obj.status in ("draft", "rejected"):
            return obj.status
        # approved -> derive on-track / behind / just-published
        # COURSE PLAN (Part B): behind = a past planned session with nothing recorded
        overdue = bool(obj.unrecorded_past_sessions(date.today()))
        if overdue:
            return "behind"
        if obj.done_units == 0:
            return "approved"     # published, nothing logged yet
        return "ontrack"

# ---------- COURSE PLAN (Part B): course outcomes ----------
class CourseOutcomeSerializer(serializers.ModelSerializer):
    level_label = serializers.CharField(source="get_level_display", read_only=True)
    subject = serializers.PrimaryKeyRelatedField(queryset=apps.get_model(SUBJECT_MODEL).objects.all())

    class Meta:
        model = CourseOutcome
        fields = ["id", "subject", "code", "text", "level", "level_label", "order"]
        read_only_fields = ["code", "order"]

    def validate_text(self, value):
        value = (value or "").strip()
        if len(value) < 5:
            raise serializers.ValidationError("Describe the outcome in a short sentence.")
        return value

    def validate_subject(self, value):
        if self.instance is not None and value.id != self.instance.subject_id:
            raise serializers.ValidationError("An outcome cannot move to another subject.")
        return value

    def create(self, validated_data):
        subject = validated_data["subject"]
        existing = CourseOutcome.objects.filter(subject=subject)
        if existing.count() >= MAX_OUTCOMES:
            raise serializers.ValidationError({"detail": f"A subject can have at most {MAX_OUTCOMES} outcomes."})
        # next free number: CO1, CO2 ... (a deleted CO's number is not reused while a later one exists)
        nums = [int(c[2:]) for c in existing.values_list("code", flat=True) if c[2:].isdigit()]
        n = max(nums, default=0) + 1
        return CourseOutcome.objects.create(code=f"CO{n}", order=n, **validated_data)
