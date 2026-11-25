# STEP 8.5: the LMS backend as a Docker image.
# The SAME image runs as: web (Django + gunicorn), worker (Celery) and beat
# (Celery Beat) - see docker-compose.yml in the project folder.
# No secrets are copied into the image (.env files are in .dockerignore).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1) Python packages first (this layer is reused when only code changes)
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && python -c "import django, celery, django_redis, redis, gunicorn, psycopg2"

# 2) The code
COPY . .

# 3) Run as a normal user, not root
RUN useradd --create-home lms \
 && mkdir -p /app/staticfiles /app/media /app/logs /data \
 && chown -R lms:lms /app /data
USER lms

EXPOSE 8000