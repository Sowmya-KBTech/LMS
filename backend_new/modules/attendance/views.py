from django.shortcuts import render
from django.contrib.auth import get_user_model

from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Attendance
from .serializers import AttendanceSerializer
from core.academics.helpers import get_parent_children
from core.academics.permissions import can_manage_academics
from core.academics.models import TeachingAssignment, Enrollment

User = get_user_model()
# ===================== ATTENDANCE =====================
class AttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # N+1 FIX (Redis/Celery work): the serializer also shows subject, course
        # and year of the teaching assignment. Load them in the SAME query,
        # otherwise every row ran 3 extra queries (90 rows = 271 queries; now 1).
        queryset = Attendance.objects.select_related(
            'student',
            'teaching_assignment__subject',
            'teaching_assignment__course',
            'teaching_assignment__year',
        )
        if user.role == 'admin':
            # Lead's decision (20-11-2026): only the main admin, super admin
            # and academic admin see attendance. Exam / accounts / IQAC admins
            # and the placement officer get nothing.
            if not can_manage_academics(user):
                return Attendance.objects.none()
        elif user.role == 'teacher':
            queryset = queryset.filter(
                teaching_assignment__teacher=user
            )
        elif user.role == 'student':
            queryset = queryset.filter(student=user)
        elif user.role == 'parent':
            children = get_parent_children(user)
            queryset = queryset.filter(student__in=children)
            child = self.request.query_params.get('child')
            if child:
                queryset = queryset.filter(student_id=child)
        else:
            return Attendance.objects.none()

        ta = self.request.query_params.get('teaching_assignment')
        if ta:
            queryset = queryset.filter(teaching_assignment_id=ta)

        date = self.request.query_params.get('date')
        if date:
            queryset = queryset.filter(date=date)

        from_date = self.request.query_params.get('from_date')
        if from_date:
            queryset = queryset.filter(date__gte=from_date)

        to_date = self.request.query_params.get('to_date')
        if to_date:
            queryset = queryset.filter(date__lte=to_date)

        return queryset.order_by('-date')

    # ── SAFETY: an admin's list must be filtered ──
    # Teachers, students and parents only ever get their own records. An
    # admin gets EVERY record of the college, so a call with no filter could
    # return a whole year of attendance at once. No screen does that (the
    # screens always send a class or dates); this stops it happening by
    # accident. Only the LIST is checked - GET /attendance/<id>/ is unchanged.
    ADMIN_LIST_FILTERS = ("teaching_assignment", "date", "from_date", "to_date")

    def list(self, request, *args, **kwargs):
        if getattr(request.user, "role", None) == "admin" and not can_manage_academics(request.user):
            return Response(
                {'error': 'Only the academic admin or super admin can view attendance.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if getattr(request.user, "role", None) == "admin" and not any(
            request.query_params.get(k) for k in self.ADMIN_LIST_FILTERS
        ):
            return Response(
                {'error': 'Please choose a class or a date range.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().list(request, *args, **kwargs)

    # ── FIX #44: CLOSE THE UNPROTECTED WRITE ENDPOINTS ──
    # As a ModelViewSet this class also exposed POST /attendance/,
    # PUT/PATCH /attendance/<id>/ and DELETE /attendance/<id>/. They had no
    # permission checks: a student or parent could change Absent -> Present,
    # create or delete their own records, and so unlock a hall ticket. No
    # screen uses them. Reading (GET) stays as it is; every save goes through
    # bulk_mark below, which checks who may mark, holidays, future dates and
    # enrolment.
    def _writes_closed(self):
        return Response(
            {'error': 'Attendance can only be saved from the attendance screen.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def create(self, request, *args, **kwargs):
        return self._writes_closed()

    def update(self, request, *args, **kwargs):
        return self._writes_closed()

    def partial_update(self, request, *args, **kwargs):
        return self._writes_closed()

    def destroy(self, request, *args, **kwargs):
        return self._writes_closed()

    # ===================== BULK MARK =====================
    @action(detail=False, methods=['post'], url_path='bulk_mark')
    def bulk_mark(self, request):
        teaching_assignment_id = request.data.get('teaching_assignment')
        date = request.data.get('date')
        hour = request.data.get('hour')
        records = request.data.get('records', [])

        if not teaching_assignment_id or not date or not hour:
            return Response(
                {'error': 'teaching_assignment, date, and hour are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            ta = TeachingAssignment.objects.get(id=teaching_assignment_id)
        except TeachingAssignment.DoesNotExist:
            return Response(
                {'error': 'Teaching assignment not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

                # ── FIX #27: no attendance on a holiday ──
        import datetime as _dt
        try:
            day = _dt.date.fromisoformat(str(date)[:10])
        except ValueError:
            return Response({'error': 'Invalid date.'}, status=status.HTTP_400_BAD_REQUEST)
        from core.academics.holidays import holiday_map
        holidays = holiday_map()
        try:
            from modules.timetable.models import Holiday
            for h in Holiday.objects.filter(date=day):
                holidays.setdefault(h.date, h.name)
        except Exception:
            pass
        if day in holidays:
            return Response(
                {'error': f"{day.strftime('%d-%m-%Y')} is a holiday ({holidays[day]}). Attendance can't be marked."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── FIX #28: no attendance for a day that hasn't happened yet ──
        from django.utils import timezone as _tz
        if day > _tz.localdate():
            return Response(
                {'error': f"{day.strftime('%d-%m-%Y')} is in the future. Attendance can only be marked for today or earlier."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ── who is allowed to mark this class ──
        # get_queryset scopes READS by role, but this write path took the
        # assignment id straight from the request body and checked nothing
        # beyond "is logged in". A student could POST here and mark themselves
        # present; a teacher could mark a colleague's class. Attendance drives
        # the 75% rule, hall ticket eligibility and the shortage fine, so the
        # write path needs at least the same scoping as the read path.
        # Lead's decision: only the main / super / academic admin may mark as
        # an admin (exam, accounts, IQAC admins and the placement officer may not).
        if request.user.role == 'admin':
            if not can_manage_academics(request.user):
                return Response(
                    {'error': 'Only the academic admin or super admin can mark attendance.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif request.user.role == 'teacher' and ta.teacher_id == request.user.id:
            pass
        else:
            return Response(
                {'error': 'You do not teach this class.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # ── ATTENDANCE WINDOW (#46, replaces the #43 Change 1 past-day lock) ──
        # Applies to EVERYONE, admin included (#43 admin fix still holds):
        #   * first entry only up to 3 working days after the class (late entry)
        #   * changes only within 3 working days of the FIRST save, then locked
        # After that the class tutor corrects it in My Class, with a reason.
        # Re-saving the same statuses is always fine.
        from .attendance_rules import session_status
        # ── ON DUTY COMES ONLY FROM AN APPROVED OD (security fix) ──
        # The server decides, not the screen: a student with an approved OD
        # for this date is always On duty, and nobody else can be - otherwise
        # choosing "OD" on the register would skip the tutor -> HOD approval.
        # Same rule as the tutor's late entry and the Excel import.
        from .models import ODRequest
        ids = []
        for record in records:
            try:
                ids.append(int(record.get('student')))
            except (TypeError, ValueError):
                pass
        od_ids = set(ODRequest.objects.filter(
            student_id__in=ids, status=ODRequest.Status.APPROVED,
            from_date__lte=day, to_date__gte=day,
        ).values_list('student_id', flat=True))
        clean_records = []
        for record in records:
            record = dict(record)
            try:
                sid = int(record.get('student'))
            except (TypeError, ValueError):
                continue
            status_value = record.get('status', 'absent')
            if sid in od_ids:
                status_value = 'duty_leave'          # approved OD always wins
            elif status_value == 'duty_leave':
                name = User.objects.filter(pk=sid).values_list('username', flat=True).first() or sid
                return Response(
                    {'error': f'{name} has no approved on-duty request for this date. '
                              'Mark Present or Absent - On duty comes from an approved OD.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            elif status_value not in ('present', 'absent'):
                return Response({'error': f'Unknown status "{status_value}".'},
                                status=status.HTTP_400_BAD_REQUEST)
            record['status'] = status_value
            clean_records.append(record)
        records = clean_records

        st = session_status(ta, day, hour)
        existing = dict(
            Attendance.objects.filter(
                teaching_assignment=ta, date=day, hour=hour
            ).values_list('student_id', 'status')
        )
        changes = []   # (student_id, old, new) — logged below (#46 Part 2)
        for record in records:
            try:
                sid = int(record.get('student'))
            except (TypeError, ValueError):
                continue
            new_status = record.get('status', 'absent')
            if sid in existing:
                if existing[sid] != new_status:
                    changes.append((sid, existing[sid], new_status))
                if existing[sid] != new_status and st['state'] == 'locked':
                    why = (f"locked by {st['lock']['by']}" if st.get('lock')
                           else f"locked. The correction window ended on {st['edit_until'].strftime('%d-%m-%Y')}")
                    return Response(
                        {'error': f'This period is {why}. Only the class in-charge can correct it now.'},
                        status=status.HTTP_403_FORBIDDEN
                    )
            elif st['state'] in ('late_closed', 'locked') or (
                    not existing and _tz.localdate() > st['late_entry_deadline']):
                return Response(
                    {'error': 'Late entry is closed. Attendance for this class had to be '
                              f"marked by {st['late_entry_deadline'].strftime('%d-%m-%Y')}. "
                              'Ask the class in-charge to enter it.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        # ── REASON FOR CHANGES INSIDE THE WINDOW (#46 Part 2) ──
        # On the first-save day changes are free. On the later window days a
        # changed status needs a reason, and each change goes into the same
        # correction log the class tutor sees (as "Subject teacher").
        change_reason = ''
        if changes and st['state'] == 'open_reason':
            change_reason = (request.data.get('reason') or '').strip()
            if len(change_reason) < 10:
                return Response(
                    {'error': 'Please give a reason for changing attendance that was saved '
                              'earlier (at least 10 characters).',
                     'needs_reason': True},
                    status=status.HTTP_400_BAD_REQUEST
                )

        from core.notifications.services import notify_parents
        saved = []
        for record in records:
            student_id = record.get('student')
            attendance_status = record.get('status', 'absent')

            # ── block if student is not enrolled in this teaching assignment ──
            is_enrolled = Enrollment.objects.filter(
                student_id=student_id,
                teaching_assignment=ta
            ).exists()

            if not is_enrolled:
                continue  # skip this record silently

            obj, created = Attendance.objects.update_or_create(
                teaching_assignment=ta,
                student_id=student_id,
                date=date,
                hour=hour,
                defaults={
                    'status': attendance_status,
                    'marked_by': request.user,
                }
            )
            saved.append(obj.id)

            # ── notify parent on absence / duty leave ──
            if attendance_status in ('absent', 'duty_leave'):
                child = User.objects.get(id=student_id)

                if attendance_status == 'duty_leave':
                    notify_parents(
                        child, "Marked on duty leave",
                        f"{child.username} was marked on duty leave in {ta.subject.name} (Hour {hour}).",
                        'announcement', ta)
                else:
                    # POINT 12, step 6: the "Low attendance warning" that was sent here
                    # on every save (fixed 75%, all semesters) is replaced by the weekly
                    # low_attendance job, which uses the #41 eligibility minimum.
                    notify_parents(
                        child, "Marked absent",
                        f"{child.username} was marked absent in {ta.subject.name} (Hour {hour}).",
                        'announcement', ta)

        if change_reason:
            from .models import AttendanceCorrection
            for sid, old_status, new_status in changes:
                att = Attendance.objects.filter(
                    teaching_assignment=ta, student_id=sid, date=day, hour=hour
                ).first()
                if att is None or att.status != new_status:
                    continue
                AttendanceCorrection.objects.create(
                    attendance=att,
                    student_id=sid,
                    teaching_assignment=ta,
                    date=day,
                    hour=int(hour),
                    old_status=old_status,
                    new_status=new_status,
                    reason=change_reason,
                    corrected_by=request.user,
                    corrected_as='admin' if request.user.role == 'admin' else 'subject_teacher',
                )

        return Response(
            {'message': f'{len(saved)} attendance records saved.', 'ids': saved},
            status=status.HTTP_200_OK
        )

    # ===================== ATTENDANCE WINDOW STATUS (#46) =====================
    @action(detail=False, methods=['get'], url_path='session_status')
    def session_status_view(self, request):
        """State of one register for the teacher screen: not_marked, late_closed,
        open_free, open_reason or locked, with the deadlines."""
        import datetime as _dt
        from .attendance_rules import session_status
        try:
            ta = TeachingAssignment.objects.get(id=request.query_params.get('teaching_assignment'))
            day = _dt.date.fromisoformat(str(request.query_params.get('date'))[:10])
            hour = int(request.query_params.get('hour'))
        except (TeachingAssignment.DoesNotExist, ValueError, TypeError):
            return Response({'error': 'teaching_assignment, date and hour are required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if request.user.role == 'teacher' and ta.teacher_id != request.user.id:
            return Response({'error': 'You do not teach this class.'}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role not in ('teacher', 'admin'):
            return Response({'error': 'Not allowed.'}, status=status.HTTP_403_FORBIDDEN)
        st = session_status(ta, day, hour)
        fmt = lambda d: d.isoformat() if d else None
        lock = st.get('lock')
        return Response({
            'state': st['state'],
            'late_entry_deadline': fmt(st['late_entry_deadline']),
            'first_saved': fmt(st['first_saved']),
            'edit_until': fmt(st['edit_until']),
            # #46 Part 3: who locked it early, if anyone
            'lock': {'kind': lock['kind'], 'by': lock['by'], 'at': lock['at']} if lock else None,
        })

    # ===================== MANUAL LOCK (#46 Part 3) =====================
    @action(detail=False, methods=['post'], url_path='lock_session')
    def lock_session(self, request):
        """The subject teacher closes one marked period early. No unlock."""
        import datetime as _dt
        from .attendance_rules import session_status
        from .models import AttendanceLock
        try:
            ta = TeachingAssignment.objects.get(id=request.data.get('teaching_assignment'))
            day = _dt.date.fromisoformat(str(request.data.get('date'))[:10])
            hour = int(request.data.get('hour'))
        except (TeachingAssignment.DoesNotExist, ValueError, TypeError):
            return Response({'error': 'teaching_assignment, date and hour are required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if request.user.role == 'admin' and not can_manage_academics(request.user):
            return Response({'error': 'Only the academic admin or super admin can lock attendance.'},
                            status=status.HTTP_403_FORBIDDEN)
        if not (request.user.role == 'admin'
                or (request.user.role == 'teacher' and ta.teacher_id == request.user.id)):
            return Response({'error': 'You do not teach this class.'}, status=status.HTTP_403_FORBIDDEN)
        st = session_status(ta, day, hour)
        if st['state'] in ('not_marked', 'late_closed'):
            return Response({'error': 'Mark and save the attendance before locking it.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if st['state'] == 'locked':
            return Response({'error': 'This period is already locked.'}, status=status.HTTP_400_BAD_REQUEST)
        AttendanceLock.objects.create(
            teaching_assignment=ta, date=day, hour=hour,
            kind='teacher_lock', locked_by=request.user,
        )
        return Response({'message': 'Attendance locked.'}, status=status.HTTP_201_CREATED)

    # ===================== OD STUDENTS FOR A DATE =====================
    @action(detail=False, methods=['get'], url_path='od_students')
    def od_students(self, request):
        """
        Returns student IDs who have an APPROVED on-duty request covering
        the given date. The teacher's mark screen uses this to pre-mark
        those students as duty_leave.
        """
        date = request.query_params.get('date')
        if not date:
            return Response({'error': 'date is required.'}, status=status.HTTP_400_BAD_REQUEST)

        from .models import ODRequest
        ids = list(
            ODRequest.objects.filter(
                status=ODRequest.Status.APPROVED,
                from_date__lte=date,
                to_date__gte=date,
            ).values_list('student_id', flat=True)
        )
        # WAVE 1: students on approved leave that day (shown as "On leave",
        # still marked Absent - leave is an excused absence, not present)
        from .student_leave_views import approved_leave_student_ids
        return Response({'student_ids': ids, 'leave_ids': approved_leave_student_ids(date)})