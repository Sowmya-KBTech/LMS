# Messaging module: teacher <-> parent messages and chat.
from django.urls import path

from .views import (
    message_contacts,
    messages_with,
    chat_contacts,
    chat_with,
)

urlpatterns = [
    path('messages/contacts/', message_contacts),
    path('messages/with/<int:user_id>/', messages_with),
    path('chat/contacts/', chat_contacts),
    path('chat/with/<int:user_id>/', chat_with),
]
