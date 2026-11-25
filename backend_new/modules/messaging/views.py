# ===================== IMPORTS =====================
from django.contrib.auth import get_user_model

from rest_framework.decorators import (  api_view, permission_classes)
from rest_framework.permissions import ( IsAuthenticated)
from rest_framework.response import Response

from core.academics.models import TeachingAssignment, Enrollment
from core.notifications.models import Notification
from core.academics.helpers import get_parent_children


User = get_user_model()


def parent_display_name(parent_user, student_ids=None):
    """'Ravi (Aarthi.R)' - parent name plus the child they belong to.

    student_ids limits the children shown to those in the caller's own classes.

    SINGLE SOURCE OF TRUTH: message_contacts() and chat_contacts() both use this.
    """
    from core.users.models import ParentProfile
    profile = ParentProfile.objects.filter(user=parent_user).first()
    if not profile:
        return parent_user.username
    kids = profile.children.all()
    if student_ids is not None:
        kids = kids.filter(id__in=student_ids)
    names = list(kids.values_list('username', flat=True))
    if not names:
        return parent_user.username
    return f"{parent_user.username} ({', '.join(names)})"

# ===================== WHO MAY MESSAGE WHOM (FIX #29) =====================
def allowed_contact_ids(user):
    """
    The user ids this user is allowed to send a message to. Same rule as the
    contact lists on screen: a parent -> the teachers of their children;
    a teacher -> the parents of students they teach. Everyone else: nobody.
    """
    from core.users.models import ParentProfile
    if user.role == 'parent':
        children = get_parent_children(user)
        ta_ids = Enrollment.objects.filter(student__in=children).values_list('teaching_assignment_id', flat=True)
        return set(TeachingAssignment.objects.filter(id__in=ta_ids).values_list('teacher_id', flat=True))
    if user.role == 'teacher':
        student_ids = Enrollment.objects.filter(teaching_assignment__teacher=user).values_list('student_id', flat=True)
        return set(ParentProfile.objects.filter(children__id__in=student_ids).values_list('user_id', flat=True))
    return set()


def _not_allowed(user_id, me):
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return True
    return uid not in allowed_contact_ids(me)

# ===================== PARENT MESSAGES =====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def message_contacts(request):
    """Who the current user can message."""
    user = request.user

    if user.role == 'parent':
        children = get_parent_children(user)
        ta_ids = Enrollment.objects.filter(
            student__in=children
        ).values_list('teaching_assignment_id', flat=True)
        teachers = User.objects.filter(
            id__in=TeachingAssignment.objects.filter(
                id__in=ta_ids
            ).values_list('teacher_id', flat=True)
        )
        data = []
        for t in teachers:
            subjects = TeachingAssignment.objects.filter(
                id__in=ta_ids, teacher=t
            ).values_list('subject__name', flat=True)
            data.append({
                'id': t.id, 'username': t.username,
                'subject': ', '.join(set(subjects)),
            })
        return Response(data)

    if user.role == 'teacher':
        ta_ids = TeachingAssignment.objects.filter(
            teacher=user
        ).values_list('id', flat=True)
        student_ids = Enrollment.objects.filter(
            teaching_assignment_id__in=ta_ids
        ).values_list('student_id', flat=True)
        from core.users.models import ParentProfile
        parents = User.objects.filter(
            id__in=ParentProfile.objects.filter(
                children__id__in=student_ids
            ).values_list('user_id', flat=True)
        ).distinct()
        return Response([{'id': p.id, 'username': parent_display_name(p, student_ids), 'subject': 'Parent'} for p in parents])

    return Response([])


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def messages_with(request, user_id):
    """GET = all messages between me and user_id. POST = send one."""
    from modules.messaging.models import ParentMessage
    from modules.messaging.serializers import ParentMessageSerializer
    me = request.user

    if request.method == 'GET':
        msgs = ParentMessage.objects.filter(
            sender_id__in=[me.id, user_id],
            receiver_id__in=[me.id, user_id],
        ).order_by('created_at')
        ParentMessage.objects.filter(sender_id=user_id, receiver=me, is_read=False).update(is_read=True)
        return Response(ParentMessageSerializer(msgs, many=True).data)

    text = (request.data.get('text') or '').strip()
    if not text:
        return Response({'detail': 'Message cannot be empty.'}, status=400)
    if _not_allowed(user_id, me):  # FIX #29
        return Response({'detail': 'You can only message the teachers / parents linked to you.'}, status=403)
    msg = ParentMessage.objects.create(sender=me, receiver_id=user_id, text=text)
    Notification.objects.create(
        recipient_id=user_id,
        title="New message",
        message=f"{me.username}: {text[:50]}",
        notification_type='chat',  # FIX #23
    )
    return Response(ParentMessageSerializer(msg).data, status=201)


# ===================== TEACHER BROADCAST TO PARENTS =====================
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def broadcast_to_parents(request):
    if request.user.role != 'teacher':
        return Response({'detail': 'Only teachers can broadcast.'}, status=403)

    from modules.messaging.models import ParentMessage
    from core.users.models import ParentProfile

    ta_id = request.data.get('teaching_assignment')
    text = (request.data.get('text') or '').strip()
    if not ta_id or not text:
        return Response({'detail': 'Subject and message are required.'}, status=400)
    # FIX #29: only for a subject this teacher actually teaches
    if not TeachingAssignment.objects.filter(id=ta_id, teacher=request.user).exists():
        return Response({'detail': 'You can only message parents of your own classes.'}, status=403)

    student_ids = Enrollment.objects.filter(
        teaching_assignment_id=ta_id
    ).values_list('student_id', flat=True)

    parent_user_ids = ParentProfile.objects.filter(
        children__id__in=student_ids
    ).values_list('user_id', flat=True).distinct()

    count = 0
    for pid in parent_user_ids:
        ParentMessage.objects.create(sender=request.user, receiver_id=pid, text=text)
        Notification.objects.create(
            recipient_id=pid,
            title="Message from teacher",
            message=f"{request.user.username}: {text[:60]}",
            notification_type='chat',  # FIX #23
        )
        count += 1

    return Response({'message': f'Sent to {count} parent(s).'})


# ===================== CHAT: CONTACTS =====================
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def chat_contacts(request):
    from core.users.models import ParentProfile
    user = request.user

    if user.role == 'parent':
        children = get_parent_children(user)
        ta_ids = Enrollment.objects.filter(
            student__in=children
        ).values_list('teaching_assignment_id', flat=True)
        teacher_ids = TeachingAssignment.objects.filter(
            id__in=ta_ids
        ).values_list('teacher_id', flat=True)
        teachers = User.objects.filter(id__in=teacher_ids).distinct()
        data = []
        for t in teachers:
            subjects = TeachingAssignment.objects.filter(
                id__in=ta_ids, teacher=t
            ).values_list('subject__name', flat=True)
            data.append({'id': t.id, 'username': t.username,
                         'subject': ', '.join(set(subjects))})
        return Response(data)

    if user.role == 'teacher':
        ta_ids = TeachingAssignment.objects.filter(
            teacher=user
        ).values_list('id', flat=True)
        student_ids = Enrollment.objects.filter(
            teaching_assignment_id__in=ta_ids
        ).values_list('student_id', flat=True)
        parent_ids = ParentProfile.objects.filter(
            children__id__in=student_ids
        ).values_list('user_id', flat=True).distinct()
        parents = User.objects.filter(id__in=parent_ids)
        return Response([{'id': p.id, 'username': parent_display_name(p, student_ids), 'subject': 'Parent'}
                         for p in parents])

    return Response([])


# ===================== CHAT: MESSAGES =====================
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def chat_with(request, user_id):
    from modules.messaging.models import ConversationMessage
    from modules.messaging.serializers import ConversationMessageSerializer
    me = request.user

    if request.method == 'GET':
        msgs = ConversationMessage.objects.filter(
            sender_id__in=[me.id, user_id],
            receiver_id__in=[me.id, user_id],
        ).order_by('created_at')
        ConversationMessage.objects.filter(
            sender_id=user_id, receiver=me, is_read=False
        ).update(is_read=True)
        return Response(ConversationMessageSerializer(msgs, many=True).data)

    text = (request.data.get('text') or '').strip()
    if not text:
        return Response({'detail': 'Message cannot be empty.'}, status=400)
    if _not_allowed(user_id, me):  # FIX #29
        return Response({'detail': 'You can only message the teachers / parents linked to you.'}, status=403)
    msg = ConversationMessage.objects.create(
        sender=me, receiver_id=user_id, text=text)
    Notification.objects.create(
        recipient_id=user_id,
        title="New message",
        message=f"{me.username}: {text[:50]}",
        notification_type='chat',  # FIX #23
    )
    return Response(ConversationMessageSerializer(msg).data, status=201)
