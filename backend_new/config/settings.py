from pathlib import Path
import os
import sys
from dotenv import load_dotenv

# ===================== BASE =====================
BASE_DIR = Path(__file__).resolve().parent.parent

# load backend/.env
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")

DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"
 
# In production the server REFUSES TO START if a setting is unsafe
# (DEBUG on, weak secret key, ...) - see config/production.py.
DJANGO_ENV = os.environ.get("DJANGO_ENV", "development").strip().lower()
PRODUCTION = DJANGO_ENV == "production"

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]


# ===================== MODULES =====================
# Which modules this college has. Set in backend/.env, for example:
#   ENABLED_MODULES=all
#   ENABLED_MODULES=learning,fees,attendance,timetable,exams
# Core (users, academics, notifications) is always on.
# Full list and rules: config/module_registry.py
from config.module_registry import resolve_enabled, installed_apps_for

ENABLED_MODULES = resolve_enabled(os.environ.get("ENABLED_MODULES", "all"))


# ===================== INSTALLED APPS (SAAS PHASE 1) =====================
# One database, one PostgreSQL schema per college (django-tenants).
#
# SHARED_APPS -> tables created ONCE, in the "public" schema: the list of
#                colleges (Tenant IDs) and their web addresses.
# TENANT_APPS -> tables created AGAIN in EVERY college's schema: users,
#                courses, attendance, fees ... everything that belongs to
#                one college. That is why the KB Tech Campus code below needs
#                no "college" field and no college filter in its queries.
SHARED_APPS = [
    'django_tenants',              # must be first
    'core.tenants',                # College (Tenant ID) + Domain
    'core.security',               # PHASE 5 PART 4: login protection (platform sign-in)

    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party (no tables of their own)
    'rest_framework',
    'corsheaders',
]

TENANT_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.admin',
    'django.contrib.sessions',
    'core.security',               # PHASE 5 PART 4: login protection (each college's own)

    # KB Tech Campus: core/ + the modules switched on (per college from Phase 3)
    *installed_apps_for(ENABLED_MODULES),
]

INSTALLED_APPS = list(SHARED_APPS) + [a for a in TENANT_APPS if a not in SHARED_APPS]

TENANT_MODEL = "tenants.College"
TENANT_DOMAIN_MODEL = "tenants.Domain"

# PLATFORM CONSOLE: a new college's address is <code>.<suffix>
#   laptop: abc.localhost      server (.env): COLLEGE_DOMAIN_SUFFIX=kbtechcampus.in
COLLEGE_DOMAIN_SUFFIX = os.environ.get("COLLEGE_DOMAIN_SUFFIX", "localhost")


# ===================== MIDDLEWARE =====================
MIDDLEWARE = [
    # SAAS PHASE 1: reads the address (abc.localhost) and switches the
    # database to that college's schema. MUST be first, so nothing runs
    # against the wrong college.
    'django_tenants.middleware.main.TenantMainMiddleware',
    'corsheaders.middleware.CorsMiddleware',   # first after the tenant switch
    # PLATFORM CONSOLE: a college switched off by KB Technosoft is refused
    'core.tenants.middleware.InactiveCollegeMiddleware',
    # Every upload has a size ceiling (core/security/uploads.py)
    'core.security.uploads.UploadLimitMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# ===================== URLS =====================
ROOT_URLCONF = 'config.urls'                   # a college's address (abc.localhost)
PUBLIC_SCHEMA_URLCONF = 'config.urls_public'   # the platform's address (localhost)


# ===================== TEMPLATES =====================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


# ===================== WSGI =====================
WSGI_APPLICATION = 'config.wsgi.application'


# ===================== DATABASE =====================
DATABASES = {
    'default': {
        # SAAS PHASE 1: PostgreSQL driver that switches schema per college
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': os.environ.get("DB_NAME", "lms_db"),
        'USER': os.environ.get("DB_USER", "postgres"),
        'PASSWORD': os.environ.get("DB_PASSWORD", ""),
        'HOST': os.environ.get("DB_HOST", "localhost"),
        'PORT': os.environ.get("DB_PORT", "5432"),
    }
}


# SAAS PHASE 1: shared tables only in "public", college tables only in college schemas
DATABASE_ROUTERS = ('django_tenants.routers.TenantSyncRouter',)

# SAAS PHASE 1: tests run inside a test college (see config/test_runner.py)
TEST_RUNNER = 'config.test_runner.TenantTestRunner'


# ===================== PASSWORD VALIDATION =====================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ===================== INTERNATIONAL =====================
LANGUAGE_CODE = 'en-us'
# FIX #7: the college runs on Indian time. With USE_TZ = True the database
# still stores UTC; this only decides how typed-in times (e.g. a lecture at
# 4:00 PM) are understood and how times are sent back to the app.
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True


# ===================== STATIC =====================
STATIC_URL = 'static/'


# ===================== MEDIA =====================
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# PHASE 4: every college's uploads go into its own folder, media/<college code>/
# (abc -> media/abc/student_photos/..., xyz -> media/xyz/...). The database keeps
# the short name; the college comes from the address. Files are served by
# core.tenants.media.college_media - only this college's folder, only when
# signed in here.
STORAGES = {
    "default": {"BACKEND": "django_tenants.files.storage.TenantFileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MULTITENANT_RELATIVE_MEDIA_ROOT = "%s"      # %s = the college's schema name

# On the server, let Nginx send the file after Django has checked it:
#   MEDIA_ACCEL_REDIRECT_PREFIX=/protected-media/
# and in Nginx:
#   location /media/           { proxy_pass http://django; }      # Django checks
#   location /protected-media/ { internal; alias /srv/kbtc/media/; }
# Empty (laptop) = Django sends the file itself.
MEDIA_ACCEL_REDIRECT_PREFIX = os.environ.get("MEDIA_ACCEL_REDIRECT_PREFIX", "")

# UPLOAD SIZE LIMITS (core/security/uploads.py) - the most one file may be, in MB.
# Screens with a smaller limit of their own keep it. Nginx: client_max_body_size 510m;
VIDEO_UPLOAD_MAX_MB = int(os.environ.get("VIDEO_UPLOAD_MAX_MB", 500))    # lecture videos
AUDIO_UPLOAD_MAX_MB = int(os.environ.get("AUDIO_UPLOAD_MAX_MB", 25))     # voice notes
IMAGE_UPLOAD_MAX_MB = int(os.environ.get("IMAGE_UPLOAD_MAX_MB", 5))      # photos
FILE_UPLOAD_MAX_MB = int(os.environ.get("FILE_UPLOAD_MAX_MB", 20))       # PDF, Word, Excel, ...


# ===================== CACHE (REDIS, from the Redis/Celery work) =====================
# REDIS_URL set   -> Redis cache (shared by all server workers).
# REDIS_URL empty -> in-memory cache, so the LMS still works without Redis.
# Every key starts with lms:<college schema>: (config/cache_keys.py), so two
# colleges never see each other's cached data.
REDIS_URL = os.environ.get("REDIS_URL", "").strip()

# `manage.py test` never needs Redis or a Celery worker: the tests use the
# in-memory cache and run every job inside the test, whatever .env says
# (Redis being stopped on the laptop must not slow down or break the tests).
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
if TESTING:
    REDIS_URL = ""

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_FUNCTION": "config.cache_keys.make_key",
            "TIMEOUT": 300,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "SOCKET_CONNECT_TIMEOUT": 2,   # seconds
                "SOCKET_TIMEOUT": 2,           # seconds
                # If Redis is down, behave like an empty cache (read from
                # PostgreSQL) instead of crashing the request.
                "IGNORE_EXCEPTIONS": True,
            },
        }
    }
    DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "kbtech-campus",
            "KEY_FUNCTION": "config.cache_keys.make_key",
            "TIMEOUT": 300,
        }
    }

# ===================== CELERY (from the Redis/Celery work) =====================
# CELERY_BROKER_URL set   -> jobs go to Redis and a separate worker runs them.
# CELERY_BROKER_URL empty -> "eager" mode: jobs run straight away inside the
#                            request (like today), so nothing breaks without a worker.
# Uses Redis database 1, so jobs never mix with the cache (database 0).
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "").strip()
if TESTING:
    CELERY_BROKER_URL = ""                 # jobs run inside the test (see TESTING above)

if CELERY_BROKER_URL:
    CELERY_RESULT_BACKEND = CELERY_BROKER_URL
    CELERY_TASK_ALWAYS_EAGER = False
else:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True

CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_EXPIRES = 3600               # seconds; job status is kept in PostgreSQL later (6.2)
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TIME_LIMIT = 300               # hard stop after 5 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 240          # task is warned after 4 minutes
CELERY_WORKER_PREFETCH_MULTIPLIER = 1      # a worker takes one job at a time
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# If Redis is down, sending a job fails after about 2 seconds instead of hanging.
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "socket_connect_timeout": 2,
    "socket_timeout": 5,
    # Docker Desktop on Windows can silently drop an idle connection; the worker
    # would then look "ready" but never receive jobs. Keep-alive + a health check
    # every 10 s make it notice and reconnect quickly.
    "socket_keepalive": True,
    "health_check_interval": 10,
}
CELERY_REDIS_SOCKET_CONNECT_TIMEOUT = 2    # same for the result store
CELERY_REDIS_SOCKET_TIMEOUT = 5
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {"retry_policy": {"timeout": 2.0}}
CELERY_TASK_PUBLISH_RETRY_POLICY = {
    "max_retries": 2, "interval_start": 0, "interval_step": 0.5, "interval_max": 1,
}

# step 8.1: scheduled jobs (replaces the Windows Task Scheduler .bat files).
# ONE Beat for the whole platform; each job goes through every active college
# (modules/automation/tasks.py). Times are India time (CELERY_TIMEZONE).
# Run exactly ONE Beat process:
#   .\venv\Scripts\celery.exe -A config beat -l info
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "nightly-jobs": {                                   # was run_daily_jobs.bat
        "task": "automation.run_daily_jobs",
        "schedule": crontab(hour=0, minute=15),          # 12:15 AM every day
    },
    "email-queue": {                                    # was run_email_queue.bat
        "task": "notifications.send_email_queue",
        "schedule": 600.0,                               # every 10 minutes
    },
    "heartbeat": {                                      # STEP 8.4 health check
        "task": "automation.heartbeat",
        "schedule": 300.0,                               # every 5 minutes
    },
}
# Beat remembers when each job last ran in this file (not committed to git)
CELERY_BEAT_SCHEDULE_FILENAME = str(BASE_DIR / "celerybeat-schedule")

# ===================== DEFAULT PK =====================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ===================== CUSTOM USER =====================
AUTH_USER_MODEL = 'users.User'


# ===================== DRF =====================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        # SAAS PHASE 1: refuses a token issued by another college
        'core.tenants.jwt.TenantJWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}


# ===================== JWT =====================
from datetime import timedelta

SIMPLE_JWT = {
    # PHASE 5 PART 5: how long one sign-in lasts (logout / password change end it sooner)
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=int(os.environ.get("JWT_ACCESS_HOURS", 24))),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ===================== LOGIN PROTECTION (PHASE 5 PART 4) =====================
# Wrong passwords counted over this many minutes (core/security/login_guard.py)
LOGIN_FAILURE_WINDOW_MINUTES = int(os.environ.get("LOGIN_FAILURE_WINDOW_MINUTES", 15))
LOGIN_LIMIT_PER_USER_AND_IP = int(os.environ.get("LOGIN_LIMIT_PER_USER_AND_IP", 5))
LOGIN_LIMIT_PER_USER = int(os.environ.get("LOGIN_LIMIT_PER_USER", 20))
LOGIN_LIMIT_PER_IP = int(os.environ.get("LOGIN_LIMIT_PER_IP", 100))
# How many proxies (Nginx) sit in front of Django: 0 on the laptop, 1 on the
# server (PHASE 5 PART 5 default). Used for the caller's real IP and for https.
TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", 1 if PRODUCTION else 0))


# ===================== EXTERNAL API KEYS =====================
GOOGLE_CALENDAR_API_KEY = os.environ.get("GOOGLE_CALENDAR_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


# ===================== CORS + CSRF =====================
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True

# ===================== EMAIL =====================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("EMAIL_HOST_USER", "")

# ===================== RAZORPAY =====================
# PHASE 3: there are NO Razorpay keys here any more. Each college saves its
# own keys in Payment settings (stored in its own schema), so each college's
# fees go to its own Razorpay account. RAZORPAY_* lines in .env are ignored.
#
# The college's secrets are stored encrypted. On the server, set a fixed key:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#   PAYMENT_ENCRYPTION_KEY=<that value>
# Empty = a key derived from DJANGO_SECRET_KEY (fine on a laptop).
PAYMENT_ENCRYPTION_KEY = os.environ.get("PAYMENT_ENCRYPTION_KEY", "")

# ===================== SECURITY (env-driven) =====================
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("DJANGO_CORS_ORIGINS", "").split(",") if o.strip()]

# SAAS PHASE 2: every college has its own address (abc.localhost:5173,
# later abc.kbtechcampus.in), so listing origins one by one cannot work.
# A pattern allows them all, e.g. in .env:
#   DJANGO_CORS_ORIGIN_REGEXES=^http://([a-z0-9]+\.)?localhost:5173$
CORS_ALLOWED_ORIGIN_REGEXES = [r.strip() for r in os.environ.get("DJANGO_CORS_ORIGIN_REGEXES", "").split(",") if r.strip()]

# CSRF accepts "*." wildcards, e.g. DJANGO_CSRF_TRUSTED_ORIGINS=http://*.localhost:5173
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS + [
    o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

# DJANGO_SECURE_COOKIES=True turns it on elsewhere, e.g. a staging test).
_secure = PRODUCTION or os.environ.get("DJANGO_SECURE_COOKIES", "False") == "True"
SESSION_COOKIE_SECURE = _secure
CSRF_COOKIE_SECURE = _secure
# http:// -> https://. Set DJANGO_SSL_REDIRECT=False only if Nginx already does it.
SECURE_SSL_REDIRECT = _secure and os.environ.get("DJANGO_SSL_REDIRECT", "True") == "True"

# Nginx talks plain http to Django and passes "X-Forwarded-Proto: https".
# Without this, Django thinks every request is http and the redirect loops.
if TRUSTED_PROXY_COUNT:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# HSTS: the browser remembers "HTTPS only" for the site AND every college
# subdomain, so nobody can be pushed onto plain http. 1 year once live;
# start lower (e.g. DJANGO_HSTS_SECONDS=3600) for the first days if unsure.
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", 31536000 if _secure else 0))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _secure
SECURE_HSTS_PRELOAD = False
# Preload = asking browser makers to hard-code HTTPS for the domain. It is very
# hard to undo, so it is a decision for after go-live, not a default.
SILENCED_SYSTEM_CHECKS = ["security.W021"]

# Safe headers on every response
SECURE_CONTENT_TYPE_NOSNIFF = True                 # no guessing file types
SECURE_REFERRER_POLICY = "same-origin"             # addresses don't leak to other sites
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"                           # nobody can frame the app (clickjacking)

SESSION_COOKIE_HTTPONLY = True                     # JavaScript can't read the session
SESSION_COOKIE_SAMESITE = "Lax"

# The Django admin page address. On the server pick something not guessable,
# e.g. DJANGO_ADMIN_URL=kb-manage-7f3a/  (bots try /admin/ all day).
ADMIN_URL = os.environ.get("DJANGO_ADMIN_URL", "admin/").strip("/") + "/"

# ===================== LOGGING (PHASE 5 PART 5) =====================
# Everything goes to the console, where Docker / the server collects it.
# Errors (500s) always show with their traceback; no secrets are logged.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO" if PRODUCTION else "WARNING")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# Last line on purpose: checks the FINAL values above. Unsafe -> server won't start.
if PRODUCTION:
    from config.production import raise_if_unsafe
    raise_if_unsafe(globals())