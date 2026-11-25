"""
Background tasks for the users app.

Redis/Celery work, step 6.1: only a 'ping' task, used by `manage.py
celery_check` to prove that Django -> Redis -> Celery worker -> back works.
It answers with the college it ran in, which proves the worker switched to
the right college (config/celery.py).
"""
from celery import shared_task
from django.db import connection


@shared_task(name="lms.ping")
def ping():
    return {"pong": True, "college": connection.schema_name}
