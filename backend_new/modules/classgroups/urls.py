# backend/classgroups/urls.py
from django.urls import path

from .views import (
    close_poll,
    create_event,
    create_poll,
    delete_message,
    group_detail,
    group_messages,
    group_settings,
    group_students,
    my_files,
    my_groups,
    pin_message,
    poll_responses,
    vote_poll,
)

urlpatterns = [
    # ================= CLASS GROUPS =================
    path("class-groups/",                                     my_groups),
    path("class-groups/files/",                               my_files),
    path("class-groups/<int:group_id>/",                      group_detail),
    path("class-groups/<int:group_id>/students/",             group_students),
    path("class-groups/<int:group_id>/messages/",             group_messages),
    path("class-groups/<int:group_id>/messages/<int:message_id>/",     delete_message),
    path("class-groups/<int:group_id>/messages/<int:message_id>/pin/", pin_message),
    path("class-groups/<int:group_id>/settings/",             group_settings),

    # ================= POLLS AND EVENTS =================
    path("class-groups/<int:group_id>/polls/",                          create_poll),
    path("class-groups/<int:group_id>/polls/<int:poll_id>/vote/",       vote_poll),
    path("class-groups/<int:group_id>/polls/<int:poll_id>/close/",      close_poll),
    path("class-groups/<int:group_id>/polls/<int:poll_id>/responses/",  poll_responses),
    path("class-groups/<int:group_id>/events/",                         create_event),
]