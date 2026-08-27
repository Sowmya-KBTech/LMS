# backend/classgroups/views.py
from datetime import date

from django.db.models import Max, Q
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from courses.models import Notification, TeachingAssignment, Year, YearTutor
from users.models import User

from .models import ROMAN, ClassGroup, ClassMessage, ClassMessageRead
from .serializers import ClassMessageSerializer, GroupSettingsSerializer, person_name

MAX_UPLOAD = 10 * 1024 * 1024   # 10 MB


# ================= ACADEMIC YEAR =================
def current_academic_year(today=None):
    t = today or date.today()
    start = t.year if t.month >= 6 else t.year - 1
    return f"{start}-{start + 1}"


# ================= NOTIFICATIONS =================
def notify(recipients, title, message):
    """Uses courses.Notification, the system the LMS already has."""
    Notification.objects.bulk_create([
        Notification(recipient=r, title=title[:200], message=(message or "")[:400],
                     notification_type="announcement")
        for r in recipients
    ])


# ================= ACCESS =================
def resolve(user, group_id):
    """
    Returns (group, role, error). role is "owner" or "student".

    Access is recomputed from the academic tables every request, so a student
    moved to another class loses access at once and a new advisor gains it,
    with no membership table to update.
    """
    group = (
        ClassGroup.objects
        .filter(id=group_id)
        .select_related("course", "year", "teaching_assignment",
                        "teaching_assignment__subject", "teaching_assignment__course",
                        "teaching_assignment__year", "teaching_assignment__teacher")
        .first()
    )
    if not group:
        return None, None, Response({"detail": "Group not found."},
                                    status=status.HTTP_404_NOT_FOUND)

    if group.owner() == user:
        return group, "owner", None

    if group.students().filter(id=user.id).exists():
        return group, "student", None

    return None, None, Response(
        {"detail": "You do not have access to this group."},
        status=status.HTTP_403_FORBIDDEN,
    )


def unread_count(group, user):
    mark = ClassMessageRead.objects.filter(group=group, user=user).first()
    qs = group.messages.filter(is_deleted=False).exclude(sender=user)
    if mark and mark.last_read_at:
        qs = qs.filter(created_at__gt=mark.last_read_at)
    return qs.count()


def group_card(group, user, role):
    students = group.students()
    owner = group.owner()
    msgs = group.messages.filter(is_deleted=False)

    return {
        "id": group.id,
        "kind": group.kind,
        "name": group.display_name,
        "subject_name": group.subject_name,
        "course_name": group._course.name,
        "year_number": group._year_number,
        "year_label": ROMAN.get(group._year_number, group._year_number),
        "academic_year": group.academic_year,
        "owner": {"id": owner.id, "name": person_name(owner)} if owner else None,
        "student_count": students.count(),
        "has_audience": students.exists(),
        "message_count": msgs.count(),
        "announcement_count": msgs.filter(message_type=ClassMessage.ANNOUNCEMENT).count(),
        "file_count": msgs.exclude(attachment="").exclude(attachment=None).count(),
        "unread": unread_count(group, user),
        "my_role": role,
        "can_post": group.can_post(user),
        "settings": {
            "announcement_only": group.announcement_only,
            "students_can_message": group.students_can_message,
            "students_can_upload": group.students_can_upload,
        },
        "can_attach": (role == "owner") or group.students_can_upload,
    }


# ================= 1. MY GROUPS =================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_groups(request):
    """
    Teacher: class groups from YearTutor + subject groups from TeachingAssignment.
    Student: their class group + one group per subject they are enrolled in.
    """
    ay = current_academic_year()
    user = request.user
    class_groups, subject_groups = [], []

    if user.role == "teacher":
        for link in YearTutor.objects.filter(teacher=user).select_related("course", "year"):
            g = ClassGroup.for_class(link.course, link.year, ay)
            class_groups.append(group_card(g, user, "owner"))

        for ta in TeachingAssignment.objects.filter(teacher=user).select_related(
                "course", "year", "subject"):
            g = ClassGroup.for_assignment(ta, ay)
            subject_groups.append(group_card(g, user, "owner"))

    elif user.role == "student":
        if user.course_id and user.year:
            yr = Year.objects.filter(course_id=user.course_id, year_number=user.year).first()
            
            # a class group exists only where a class advisor exists: same rule
            # as the teacher branch above, so a student never lands in an
            # ownerless group with no staff in it.
            if yr and YearTutor.objects.filter(course_id=user.course_id, year=yr).exists():
                g = ClassGroup.for_class(user.course, yr, ay)
                class_groups.append(group_card(g, user, "student"))

        for ta in TeachingAssignment.objects.filter(
                enrollments__student=user).distinct().select_related(
                "course", "year", "subject", "teacher"):
            g = ClassGroup.for_assignment(ta, ay)
            subject_groups.append(group_card(g, user, "student"))

    else:
        return Response({"class_groups": [], "subject_groups": [], "academic_year": ay,
                         "detail": "Class groups are for teachers and students."})

    return Response({
        "academic_year": ay,
        "class_groups": class_groups,
        "subject_groups": subject_groups,
        "count": len(class_groups) + len(subject_groups),
    })


# ================= 2. GROUP DETAIL =================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def group_detail(request, group_id):
    group, role, err = resolve(request.user, group_id)
    if err:
        return err

    data = group_card(group, request.user, role)
    data["department"] = ", ".join(sorted(
        {s.department.name for s in group.students() if s.department_id}
    )) or "\u2014"

    recent = group.messages.filter(is_deleted=False).select_related("sender").order_by("-created_at")[:4]
    data["recent_activity"] = ClassMessageSerializer(
        recent, many=True, context={"request": request}).data
    return Response(data)


# ================= 3. STUDENTS =================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def group_students(request, group_id):
    """
    Class list. A student sees names and register numbers only — attendance
    and marks are never shown to a classmate.
    """
    group, role, err = resolve(request.user, group_id)
    if err:
        return err

    students = list(group.students())
    q = (request.query_params.get("q") or "").strip().lower()

    att = {}
    if role == "owner":
        from mentoring.utils import attendance_map
        att = attendance_map(students)

    rows = []
    for s in students:
        name = person_name(s)
        if q and q not in f"{name} {s.roll_number or ''}".lower():
            continue
        row = {
            "id": s.id, "name": name, "roll_number": s.roll_number,
            "semester": s.semester, "batch_year": s.batch_year,
        }
        if role == "owner":
            a = att.get(s.id)
            row["email"] = s.email
            row["attendance"] = a
            row["status"] = "Warning" if (a is not None and a < 75) else "Active"
        rows.append(row)

    rows.sort(key=lambda r: (r["roll_number"] or "", r["name"]))
    return Response({"count": len(rows), "my_role": role, "results": rows})


# ================= 4. CONVERSATION =================
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def group_messages(request, group_id):
    """
    One conversation: text, attachments and announcements in the same thread.
    ?type=announcement filters to announcements only.
    """
    group, role, err = resolve(request.user, group_id)
    if err:
        return err

    # ---------- POST ----------
    if request.method == "POST":
        if not group.has_audience():
            return Response({
                "detail": (
                    "This group has no enrolled students, so nothing can be sent. "
                    "Ask the office to enrol students in this subject."
                ),
                "reason": "no_audience",
            }, status=status.HTTP_409_CONFLICT)

        if not group.can_post(request.user):
            reason = ("This group is in announcement-only mode."
                      if group.announcement_only
                      else "Your teacher has turned off student messages in this group.")
            return Response({"detail": reason}, status=status.HTTP_403_FORBIDDEN)

        mtype = (request.data.get("message_type") or ClassMessage.TEXT).strip()
        text = (request.data.get("text") or "").strip()
        title = (request.data.get("title") or "").strip()
        att = request.FILES.get("attachment")

        if mtype == ClassMessage.ANNOUNCEMENT and role != "owner":
            return Response({"detail": "Only the teacher can post an announcement."},
                            status=status.HTTP_403_FORBIDDEN)
        if mtype == ClassMessage.ANNOUNCEMENT and not title:
            return Response({"detail": "An announcement needs a title."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Students may attach only when the teacher has turned it on for this
        # group. Off by default, so a class file area does not fill with
        # assignment submissions that belong in the Assignments module.
        if att and role != "owner" and not group.students_can_upload:
            return Response(
                {"detail": "Your teacher has not allowed student attachments in this group."},
                status=status.HTTP_403_FORBIDDEN)
        if att and att.size > MAX_UPLOAD:
            return Response({"detail": "File is larger than 10 MB."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not text and not att:
            return Response({"detail": "Write something or attach a file."},
                            status=status.HTTP_400_BAD_REQUEST)

        m = ClassMessage.objects.create(
            group=group, sender=request.user,
            message_type=(ClassMessage.ANNOUNCEMENT
                          if mtype == ClassMessage.ANNOUNCEMENT else ClassMessage.TEXT),
            title=title, text=text, attachment=att,
            is_pinned=(str(request.data.get("is_pinned")).lower() == "true"
                       and role == "owner"),
        )

        # ---------- notify everyone in the group except the sender ----------
        # A group message is for the whole group, so a student posting must
        # reach their classmates too, not only the teacher. Excluding the
        # sender stops the bell counting your own message.
        label = group.display_name
        owner = group.owner()

        audience = list(group.students())
        if owner and owner.id != request.user.id:
            audience.append(owner)
        audience = [u for u in audience if u.id != request.user.id]

        who = "" if role == "owner" else f" \u2014 {person_name(request.user)}"
        heading = (
            f"\U0001F4E2 {label} \u2014 {title}"
            if m.message_type == ClassMessage.ANNOUNCEMENT and title
            else f"{label}{who}"
        )
        body = text or (
            "Sent a voice note"
            if str(m.attachment_name).lower().endswith((".webm", ".m4a", ".mp3", ".ogg", ".wav"))
            else f"Shared a file: {m.attachment_name}" if m.attachment_name else "New message"
        )
        notify(audience, heading, body)

        return Response(ClassMessageSerializer(m, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)

    # ---------- GET ----------
    qs = group.messages.filter(is_deleted=False).select_related("sender")
    if request.query_params.get("type") == "announcement":
        qs = qs.filter(message_type=ClassMessage.ANNOUNCEMENT)

    unread = unread_count(group, request.user)

    latest = qs.aggregate(m=Max("created_at"))["m"]
    if latest:
        ClassMessageRead.objects.update_or_create(
            group=group, user=request.user, defaults={"last_read_at": latest}
        )

    blocked = None
    if not group.has_audience():
        blocked = ("This group has no enrolled students. Nothing can be sent until "
                   "the office enrols students in this subject.")
    elif not group.can_post(request.user):
        blocked = ("This group is in announcement-only mode."
                   if group.announcement_only
                   else "Your teacher has turned off student messages in this group.")

    return Response({
        "group": group_card(group, request.user, "owner" if group.owner() == request.user else "student"),
        "can_post": group.can_post(request.user) and group.has_audience(),
        "blocked_reason": blocked,
        "unread_before_this_load": unread,
        "count": qs.count(),
        "results": ClassMessageSerializer(qs, many=True, context={"request": request}).data,
    })


# ================= 5. MESSAGE ACTIONS =================
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_message(request, group_id, message_id):
    """Soft delete. Own message, or the teacher removing a student's."""
    group, role, err = resolve(request.user, group_id)
    if err:
        return err

    m = ClassMessage.objects.filter(id=message_id, group=group, is_deleted=False).first()
    if not m:
        return Response({"detail": "Message not found."}, status=status.HTTP_404_NOT_FOUND)
    if m.sender_id != request.user.id and role != "owner":
        return Response({"detail": "You can only delete your own message."},
                        status=status.HTTP_403_FORBIDDEN)

    m.is_deleted = True
    m.deleted_by = request.user
    m.save(update_fields=["is_deleted", "deleted_by"])
    return Response({"detail": "Message removed. The record is kept."})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pin_message(request, group_id, message_id):
    group, role, err = resolve(request.user, group_id)
    if err:
        return err
    if role != "owner":
        return Response({"detail": "Only the teacher can pin an announcement."},
                        status=status.HTTP_403_FORBIDDEN)

    m = ClassMessage.objects.filter(id=message_id, group=group, is_deleted=False).first()
    if not m:
        return Response({"detail": "Message not found."}, status=status.HTTP_404_NOT_FOUND)
    if m.message_type != ClassMessage.ANNOUNCEMENT:
        return Response({"detail": "Only an announcement can be pinned."},
                        status=status.HTTP_400_BAD_REQUEST)

    m.is_pinned = not m.is_pinned
    m.save(update_fields=["is_pinned"])
    return Response({"is_pinned": m.is_pinned})


# ================= 6. SHARED FILES =================
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_files(request):
    """
    Every attachment from every group this person belongs to, in one list.
    A filtered view of ClassMessage, not a second file store.

    ?group=<id>  one group only
    ?kind=class|subject
    ?q=          search the filename
    """
    ay = current_academic_year()
    user = request.user
    groups = []

    if user.role == "teacher":
        for link in YearTutor.objects.filter(teacher=user).select_related("course", "year"):
            groups.append(ClassGroup.for_class(link.course, link.year, ay))
        for ta in TeachingAssignment.objects.filter(teacher=user).select_related(
                "course", "year", "subject"):
            groups.append(ClassGroup.for_assignment(ta, ay))
    elif user.role == "student":
        if user.course_id and user.year:
            yr = Year.objects.filter(course_id=user.course_id, year_number=user.year).first()
            if yr:
                groups.append(ClassGroup.for_class(user.course, yr, ay))
        for ta in TeachingAssignment.objects.filter(
                enrollments__student=user).distinct().select_related(
                "course", "year", "subject"):
            groups.append(ClassGroup.for_assignment(ta, ay))

    kind = request.query_params.get("kind")
    if kind in (ClassGroup.CLASS, ClassGroup.SUBJECT):
        groups = [g for g in groups if g.kind == kind]

    one = request.query_params.get("group")
    if one:
        groups = [g for g in groups if str(g.id) == str(one)]

    if not groups:
        return Response({"count": 0, "results": []})

    qs = (
        ClassMessage.objects
        .filter(group__in=groups, is_deleted=False)
        .exclude(attachment="").exclude(attachment=None)
        .select_related("sender", "group", "group__course", "group__year",
                        "group__teaching_assignment__subject")
        .order_by("-created_at")
    )
    q = (request.query_params.get("q") or "").strip()
    if q:
        qs = qs.filter(attachment_name__icontains=q)

    from .serializers import size_label
    rows = [{
        "id": m.id,
        "message_id": m.id,
        "group_id": m.group_id,
        "group_name": m.group.display_name,
        "group_kind": m.group.kind,
        "name": m.attachment_name,
        "size": m.attachment_size,
        "size_label": size_label(m.attachment_size),
        "url": request.build_absolute_uri(m.attachment.url),
        "uploaded_by": person_name(m.sender),
        "is_announcement": m.message_type == ClassMessage.ANNOUNCEMENT,
        "created_at": m.created_at,
    } for m in qs]

    return Response({"count": len(rows), "results": rows})


# ================= 7. SETTINGS =================
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def group_settings(request, group_id):
    group, role, err = resolve(request.user, group_id)
    if err:
        return err
    if request.method == "PATCH" and role != "owner":
        return Response({"detail": "Only the teacher can change group settings."},
                        status=status.HTTP_403_FORBIDDEN)

    if request.method == "PATCH":
        ser = GroupSettingsSerializer(group, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    return Response(GroupSettingsSerializer(group).data)