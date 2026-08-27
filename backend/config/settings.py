from pathlib import Path
import os
from dotenv import load_dotenv

# ===================== BASE =====================
BASE_DIR = Path(__file__).resolve().parent.parent

# load backend/.env
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")

DEBUG = True

ALLOWED_HOSTS = []


# ===================== INSTALLED APPS =====================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Custom apps
    'users',
    'courses',
    'timetable',
    'attendance',
    'exams',
    'events',
    'teachingplan',
    'mentoring',
    'classgroups',

    # Third-party
    'rest_framework',
    'corsheaders',
]


# ===================== MIDDLEWARE =====================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',   # MUST BE FIRST
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]


# ===================== URLS =====================
ROOT_URLCONF = 'config.urls'


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
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get("DB_NAME", "lms_db"),
        'USER': os.environ.get("DB_USER", "postgres"),
        'PASSWORD': os.environ.get("DB_PASSWORD", ""),
        'HOST': os.environ.get("DB_HOST", "localhost"),
        'PORT': os.environ.get("DB_PORT", "5432"),
    }
}


# ===================== PASSWORD VALIDATION =====================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ===================== INTERNATIONAL =====================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# ===================== STATIC =====================
STATIC_URL = 'static/'


# ===================== MEDIA =====================
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# ===================== DEFAULT PK =====================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ===================== CUSTOM USER =====================
AUTH_USER_MODEL = 'users.User'


# ===================== DRF =====================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}


# ===================== JWT =====================
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=24),
    'AUTH_HEADER_TYPES': ('Bearer',),
}


# ===================== EXTERNAL API KEYS =====================
GOOGLE_CALENDAR_API_KEY = os.environ.get("GOOGLE_CALENDAR_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


# ===================== CORS + CSRF =====================
CORS_ALLOW_ALL_ORIGINS = True   # dev only — lock this down before deployment
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",   # Vite dev server
]