from django.urls import path

from . import views

urlpatterns = [
    path("", views.importer_list, name="dataio-list"),
    path("<slug:key>/template/", views.template, name="dataio-template"),
    path("<slug:key>/export/", views.export, name="dataio-export"),
    path("<slug:key>/history/", views.history, name="dataio-history"),
    # STEP 7.1: preview / import run by the Celery worker
    path("<slug:key>/start/", views.start, name="dataio-start"),
]
