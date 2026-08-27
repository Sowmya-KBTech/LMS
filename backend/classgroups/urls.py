# backend/classgroups/urls.py
from django.urls import path

from .views import (
    delete_message,
    group_detail,
    group_messages,
    group_settings,
    group_students,
    my_files,
    my_groups,
    pin_message,
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
]
