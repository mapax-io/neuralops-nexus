"""
Django settings for core project.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-zj(1$&@l(309znsv2&p3h%8hy571$2+!yh+niu)h3x!btilq36'
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'ninja',
    'nucleus',
    'authn',
    'guardian',
]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'guardian.backends.ObjectPermissionBackend',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # must be first
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# =========================================================
# CORS — allow any origin in development
# =========================================================
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB"),
        "USER": os.getenv("POSTGRES_USER"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
        "HOST": os.getenv("POSTGRES_HOST"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = "nucleus.User"

# =========================================================
# Supabase JWT verification
# =========================================================

SUPABASE_URL = "https://xgfsxikypxjhqlutiepw.supabase.co"
SUPABASE_JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
SUPABASE_JWT_ISSUER = f"{SUPABASE_URL}/auth/v1"
SUPABASE_JWT_AUDIENCE = "authenticated"
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# =========================================================
# NeuralOps
# =========================================================

NEURALOPS_INSTALL_TOKEN = os.getenv("NEURALOPS_INSTALL_TOKEN", "")
SUPABASE_DEVICE_REQUEST_URL = os.getenv(
    "SUPABASE_DEVICE_REQUEST_URL",
    "https://xgfsxikypxjhqlutiepw.supabase.co/functions/v1/device-request",
)
SUPABASE_DEVICE_POLL_URL = os.getenv(
    "SUPABASE_DEVICE_POLL_URL",
    "https://xgfsxikypxjhqlutiepw.supabase.co/functions/v1/device-poll",
)
NEURALOPS_PORTAL_URL = os.getenv(
    "NEURALOPS_PORTAL_URL",
    "https://neuralops-nexus-auth.mapax.io",
)

# =========================================================
# Celery — Async Task Queue
# =========================================================

_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CELERY_BROKER_URL = _REDIS_URL
CELERY_RESULT_BACKEND = _REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 35
CELERY_TASK_SOFT_TIME_LIMIT = 60 * 31
CELERY_TASK_DEFAULT_QUEUE = "neuralops"
