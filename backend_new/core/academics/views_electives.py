
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.academics.permissions import can_manage_academics

from . import electives as rules
from .models import Course, Enrollment, TeachingAssignment, Year
from .models_electives import ElectiveChange, ElectiveGroup, ElectiveOption, ElectiveSetting


# ===================== HELPERS =====================
def _name(user):
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.username


def _error(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": message}, status=code)


def _validation_message(exc):
    if hasattr(exc, "message_dict"):
        return " ".join(m for msgs in exc.message_dict.values() for m in msgs)
    return " ".join(exc.messages)


def _option_data(option, seats=None):
    ta = option.teaching_assignment
    taken = seats.get(ta.id, 0) if seats is not None else option.seats_taken
    return {
        "id": option.id,
        "teaching_assignment": ta.id,
        "subject": ta.subject.name,
        "code": ta.subject.code or "",
        "credits": ta.subject.credits,
        "teacher_name": _name(ta.teacher),
        "seat_limit": option.seat_limit,
        "seats_taken": taken,
        "is_full": option.seat_limit is not None and taken >= option.seat_limit,
        # CBCS PART B: which course it is taught to (open electives) and its prerequisites
        "course_name": ta.course.name if ta.course_id else "",
        "requires": [{"id": s.id, "code": s.code or "", "name": s.name} for s in option.requires.all()],
    }


def _seat_counts(options):
    from django.db.models import Count
    ta_ids = [o.teaching_assignment_id for o in options]
    return dict(Enrollment.objects.filter(teaching_assignment_id__in=ta_ids)
                .values_list("teaching_assignment_id").annotate(n=Count("id")))


def _group_data(group, with_options=True):
    data = {
        "id": group.id,
        "course": group.course_id,
        "course_name": group.course.name,
        "year": group.year_id,
        "year_number": group.year.year_number,
        "semester": group.semester,
        "name": group.name,
        "department": group.department_id,
        "department_name": group.department.name if group.department_id else "",
        "picks": group.picks,
        "opens_at": group.opens_at,
        "closes_at": group.closes_at,
        "window": group.window_state(),
        "open_elective": group.open_elective,                     # CBCS PART B
        "open_to": [c.id for c in group.open_to.all()],
        "open_to_names": [c.name for c in group.open_to.all()],
    }
    if with_options:
        options = list(group.options.select_related("teaching_assignment__subject", "teaching_assignment__course",
                                                    "teaching_assignment__teacher").prefetch_related("requires"))
        seats = _seat_counts(options)
        data["options"] = [_option_data(o, seats) for o in options]
    return data


def _get_group(user, pk):
    group = ElectiveGroup.objects.select_related("course", "year", "department").filter(pk=pk).first()
    if group is None:
        return None, _error("Elective group not found.", status.HTTP_404_NOT_FOUND)
    if not rules.can_manage_group(user, group):
        return None, _error("You can't manage electives for this class.", status.HTTP_403_FORBIDDEN)
    return group, None


def _get_option(user, pk):
    option = (ElectiveOption.objects
              .select_related("group__course", "group__year", "group__department",
                              "teaching_assignment__subject", "teaching_assignment__teacher")
              .filter(pk=pk).first())
    if option is None:
        return None, _error("Elective option not found.", status.HTTP_404_NOT_FOUND)
    if not rules.can_manage_group(user, option.group):
        return None, _error("You can't manage electives for this class.", status.HTTP_403_FORBIDDEN)
    return option, None


def _date(value):
    if value in (None, ""):
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise ValidationError({"date": f"'{value}' is not a valid date and time."})
    return parsed


# ===================== SETTING =====================
@api_view(["GET", "PUT"])
@permission_classes([IsAuthenticated])
def elective_setting(request):
    setting = ElectiveSetting.current()
    if request.method == "PUT":
        if not can_manage_academics(request.user):
            return _error("Only the admin can change who selects electives.", status.HTTP_403_FORBIDDEN)
        mode = request.data.get("mode")
        if mode not in (ElectiveSetting.STUDENTS, ElectiveSetting.STAFF):
            return _error('mode must be "students" or "staff".')
        setting.mode = mode
        setting.updated_by = request.user
        setting.save()
    return Response({
        "mode": setting.mode,
        "mode_display": setting.get_mode_display(),
        "students_choose": setting.students_choose,
        "updated_at": setting.updated_at,
        "can_edit": can_manage_academics(request.user),
    })


# ===================== GROUPS =====================
def _apply_group_fields(group, data, user, creating):
    """Copy allowed fields from request data onto group. Raises ValidationError."""
    if creating or "course" in data:
        group.course = Course.objects.filter(pk=data.get("course")).first()
        if group.course is None:
            raise ValidationError({"course": "Choose a course."})
    if creating or "year" in data:
        group.year = Year.objects.filter(pk=data.get("year")).first()
        if group.year is None:
            raise ValidationError({"year": "Choose a year."})
    if creating or "semester" in data:
        try:
            group.semester = int(data.get("semester"))
        except (TypeError, ValueError):
            raise ValidationError({"semester": "Choose a semester."})
    if creating or "name" in data:
        group.name = (data.get("name") or "").strip()
        if not group.name:
            raise ValidationError({"name": "Give the group a name, e.g. Professional Elective I."})
    if "picks" in data:
        try:
            group.picks = int(data.get("picks"))
        except (TypeError, ValueError):
            raise ValidationError({"picks": "How many electives each student takes must be a number."})
    if "opens_at" in data:
        group.opens_at = _date(data.get("opens_at"))
    if "closes_at" in data:
        group.closes_at = _date(data.get("closes_at"))
    if "open_elective" in data:                                   # CBCS PART B
        new = data.get("open_elective") in (True, "true", "True", "1", 1)
        if group.pk and new != group.open_elective and group.options.exists():
            raise ValidationError({"open_elective": "Remove the options first to change whether this is an open elective."})
        group.open_elective = new

    if creating or "department" in data:
        from core.users.models import Department
        dept_id = data.get("department")
        if can_manage_academics(user):
            group.department = Department.objects.filter(pk=dept_id).first() if dept_id else None
        else:
            # a HOD can only create / keep groups for their own department
            mine = Department.objects.filter(hod=user)
            group.department = mine.filter(pk=dept_id).first() if dept_id else mine.first()
            if group.department is None:
                raise ValidationError({"department": "You can only manage electives for your own department."})
    group.full_clean(exclude=["created_by"])


def _set_open_to(group, data):
    """CBCS PART B: the courses an open elective is offered to (none = every course)."""
    if "open_to" not in data:
        return
    ids = [int(c) for c in (data.get("open_to") or []) if str(c).isdigit()]
    group.open_to.set(Course.objects.filter(pk__in=ids) if group.open_elective else [])


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def group_list(request):
    user = request.user
    if request.method == "GET":
        groups = rules.manageable_groups(user)
        for key in ("course", "year", "semester"):
            if request.query_params.get(key):
                groups = groups.filter(**{f"{key}_id" if key != "semester" else key: request.query_params[key]})
        return Response([_group_data(g) for g in groups])

    from core.users.models import Department
    if not (can_manage_academics(user) or Department.objects.filter(hod=user).exists()):
        return _error("Only the admin or a HOD can create elective groups.", status.HTTP_403_FORBIDDEN)
    group = ElectiveGroup(created_by=user)
    try:
        _apply_group_fields(group, request.data, user, creating=True)
        group.save()
        _set_open_to(group, request.data)
    except ValidationError as exc:
        return _error(_validation_message(exc))
    except IntegrityError:
        return _error("This class already has a group with that name.")
    return Response(_group_data(group), status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def group_detail(request, pk):
    group, err = _get_group(request.user, pk)
    if err:
        return err
    if request.method == "GET":
        return Response(_group_data(group))
    if request.method == "DELETE":
        if Enrollment.objects.filter(teaching_assignment__elective_option__group=group).exists():
            return _error("Students already hold electives in this group. Remove them first.")
        group.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    try:
        _apply_group_fields(group, request.data, request.user, creating=False)
        group.save()
        _set_open_to(group, request.data)
    except ValidationError as exc:
        return _error(_validation_message(exc))
    except IntegrityError:
        return _error("This class already has a group with that name.")
    return Response(_group_data(group))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def group_available(request, pk):
    """Elective teaching assignments of this class that aren't in any group yet."""
    group, err = _get_group(request.user, pk)
    if err:
        return err
    tas = TeachingAssignment.objects.filter(subject__semester=group.semester, subject__is_elective=True,
                                            elective_option__isnull=True)
    if not group.open_elective:                                   # CBCS PART B: open = any course
        tas = tas.filter(course=group.course, year=group.year)
    tas = tas.select_related("subject", "teacher", "course").order_by("course__name", "subject__name")
    return Response([{"teaching_assignment": ta.id, "subject": ta.subject.name, "code": ta.subject.code or "",
                      "teacher_name": _name(ta.teacher), "course_name": ta.course.name if ta.course_id else ""}
                     for ta in tas])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def group_add_option(request, pk):
    group, err = _get_group(request.user, pk)
    if err:
        return err
    ta = TeachingAssignment.objects.select_related("subject").filter(pk=request.data.get("teaching_assignment")).first()
    if ta is None:
        return _error("Choose a teaching assignment.")
    seat_limit = request.data.get("seat_limit")
    try:
        seat_limit = int(seat_limit) if seat_limit not in (None, "") else None
        if seat_limit is not None and seat_limit < 1:
            raise ValueError
    except (TypeError, ValueError):
        return _error("Seat limit must be a whole number above 0, or blank for no limit.")
    option = ElectiveOption(group=group, teaching_assignment=ta, seat_limit=seat_limit)
    try:
        option.full_clean()
        option.save()
    except ValidationError as exc:
        msg = _validation_message(exc)
        if "teaching assignment" in msg.lower() and "already exists" in msg.lower():
            msg = f"{ta.subject.name} is already in an elective group."
        return _error(msg)
    return Response(_option_data(option), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def option_detail(request, pk):
    option, err = _get_option(request.user, pk)
    if err:
        return err
    if request.method == "DELETE":
        if option.seats_taken:
            return _error(f"{option.seats_taken} student(s) hold {option.teaching_assignment.subject.name}. "
                          f"Move them first.")
        option.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if "seat_limit" in request.data:
        raw = request.data.get("seat_limit")
        try:
            limit = int(raw) if raw not in (None, "") else None
            if limit is not None and limit < 1:
                raise ValueError
        except (TypeError, ValueError):
            return _error("Seat limit must be a whole number above 0, or blank for no limit.")
        if limit is not None and limit < option.seats_taken:
            return _error(f"{option.seats_taken} students already hold it - the limit can't be below that.")
        option.seat_limit = limit
        option.save(update_fields=["seat_limit"])
    if "requires" in request.data:                                # CBCS PART B: prerequisites
        from .models import Subject
        ids = [int(x) for x in (request.data.get("requires") or []) if str(x).isdigit()]
        subjects = list(Subject.objects.filter(pk__in=ids))
        if len(subjects) != len(set(ids)):
            return _error("Unknown subject.")
        own = option.teaching_assignment.subject
        if any(s.id == own.id or s.semester >= own.semester for s in subjects):
            return _error("A prerequisite must be a subject of an earlier semester.")
        option.requires.set(subjects)
    return Response(_option_data(option))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def option_prerequisite_choices(request, pk):
    """CBCS PART B: subjects of earlier semesters of the option's course, to pick prerequisites from."""
    option, err = _get_option(request.user, pk)
    if err:
        return err
    from .models import Subject
    ta = option.teaching_assignment
    subjects = (Subject.objects.filter(year__course_id=ta.course_id, semester__lt=ta.subject.semester)
                .order_by("semester", "code", "name"))
    return Response([{"id": s.id, "code": s.code or "", "name": s.name, "semester": s.semester} for s in subjects])


# ===================== ALLOCATION (STAFF) =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def group_students(request, pk):
    group, err = _get_group(request.user, pk)
    if err:
        return err
    options = {o.teaching_assignment_id: o for o in group.options.select_related("teaching_assignment__subject")}
    held = {}
    for sid, ta_id in Enrollment.objects.filter(teaching_assignment_id__in=options.keys()).values_list(
            "student_id", "teaching_assignment_id"):
        held.setdefault(sid, []).append(options[ta_id])
    rows = []
    for st in rules.class_students(group):
        mine = held.get(st.id, [])
        rows.append({
            "student": st.id,
            "name": _name(st),
            "roll_number": st.roll_number or "",
            "options": [{"id": o.id, "subject": o.teaching_assignment.subject.name} for o in mine],
            "complete": len(mine) >= group.picks,
        })
    return Response({
        "group": _group_data(group, with_options=True),
        "students": rows,
        "not_chosen": sum(1 for r in rows if not r["options"]),
    })


def _student_and_option(request):
    from core.users.models import User
    student = User.objects.filter(pk=request.data.get("student"), role="student").first()
    option = (ElectiveOption.objects.select_related("group__year", "teaching_assignment__subject")
              .filter(pk=request.data.get("option")).first())
    return student, option


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def allocate(request):
    student, option = _student_and_option(request)
    if student is None or option is None:
        return _error("Choose a student and an elective.")
    try:
        change = rules.choose(student, option, by=request.user, reason=request.data.get("reason", ""))
    except rules.ElectiveError as exc:
        return _error(str(exc))
    return Response({"detail": "Already allocated." if change is None else
                     f"{_name(student)}: {option.teaching_assignment.subject.name}.",
                     "changed": change is not None})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def remove(request):
    student, option = _student_and_option(request)
    if student is None or option is None:
        return _error("Choose a student and an elective.")
    try:
        change = rules.drop(student, option, by=request.user, reason=request.data.get("reason", ""))
    except rules.ElectiveError as exc:
        return _error(str(exc))
    return Response({"detail": "Removed." if change else "The student didn't have this elective.",
                     "changed": change is not None})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def option_assign_class(request, pk):
    option, err = _get_option(request.user, pk)
    if err:
        return err
    try:
        result = rules.assign_whole_class(option, by=request.user)
    except rules.ElectiveError as exc:
        return _error(str(exc))
    subject = option.teaching_assignment.subject.name
    message = f"{result['assigned']} student(s) given {subject}."
    if result["already"]:
        message += f" {result['already']} already had it."
    if result["kept_other"]:
        message += f" {len(result['kept_other'])} kept their other elective."
    return Response({**result, "detail": message})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def group_changes(request, pk):
    group, err = _get_group(request.user, pk)
    if err:
        return err
    changes = (ElectiveChange.objects.filter(group=group)
               .select_related("student", "changed_by", "from_option__teaching_assignment__subject",
                               "to_option__teaching_assignment__subject")[:500])

    def subj(o):
        return o.teaching_assignment.subject.name if o else ""
    return Response([{
        "id": c.id, "student": _name(c.student), "roll_number": c.student.roll_number or "",
        "from": subj(c.from_option), "to": subj(c.to_option),
        "changed_by": _name(c.changed_by), "reason": c.reason, "changed_at": c.changed_at,
    } for c in changes])


# ===================== STUDENT =====================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_electives_v2(request):
    user = request.user
    if getattr(user, "role", None) != "student":
        return _error("Only students have electives.", status.HTTP_403_FORBIDDEN)
    setting = ElectiveSetting.current()
    groups = []
    for g in rules.groups_for_student(user):
        data = _group_data(g)
        held = {o.id for o in rules.current_options(user, g)}
        passed = rules.passed_subjects(user)
        by_id = {o.id: o for o in g.options.all()}
        for o in data["options"]:
            o["chosen"] = o["id"] in held
            o["blocked"] = rules.blocked_reason(user, by_id[o["id"]], passed)      # CBCS PART B
        data["can_choose"] = setting.students_choose and g.is_open()
        groups.append(data)
    return Response({"mode": setting.mode, "students_choose": setting.students_choose, "groups": groups})


def _student_option(request):
    return (ElectiveOption.objects.select_related("group__year", "teaching_assignment__subject")
            .filter(pk=request.data.get("option")).first())


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_choose(request):
    if getattr(request.user, "role", None) != "student":
        return _error("Only students choose electives.", status.HTTP_403_FORBIDDEN)
    option = _student_option(request)
    if option is None:
        return _error("Choose an elective.")
    try:
        rules.choose(request.user, option, by=request.user)
    except rules.ElectiveError as exc:
        return _error(str(exc))
    return Response({"detail": f"You chose {option.teaching_assignment.subject.name}."})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def my_drop(request):
    if getattr(request.user, "role", None) != "student":
        return _error("Only students choose electives.", status.HTTP_403_FORBIDDEN)
    option = _student_option(request)
    if option is None:
        return _error("Choose an elective.")
    try:
        rules.drop(request.user, option, by=request.user)
    except rules.ElectiveError as exc:
        return _error(str(exc))
    return Response({"detail": f"Removed {option.teaching_assignment.subject.name}."})