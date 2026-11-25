from django.urls import path

from . import views

# mounted at /api/surveys/ (config/module_registry.py)
urlpatterns = [
    path("manage/", views.manage_list),
    path("manage/<int:pk>/", views.manage_detail),
    path("manage/<int:pk>/publish/", views.manage_publish),
    path("manage/<int:pk>/close/", views.manage_close),
    path("manage/<int:pk>/results/", views.manage_results),
    path("options/", views.options),
    path("templates/", views.templates),
    path("my/", views.my_list),
    path("my/<int:pk>/", views.my_detail),
    path("my/<int:pk>/submit/", views.my_submit),
]
