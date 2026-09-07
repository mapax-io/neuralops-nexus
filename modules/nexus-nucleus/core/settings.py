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
    'django_celery_beat',
    'nucleus',
    'authn',
    'chat',
    'intelligence',
    'workspace',
    'internal',
    'context',
    'scheduling',
    'guardian',
]

# =========================================================
# Media files — uploaded context sources, attachments, etc.
# =========================================================
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

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

# The identity project this server verifies tokens against. The image bakes
# the shared platform project as the default (neuralops/Dockerfile ENV); a
# deployment that runs its own Supabase project sets SUPABASE_URL and
# SUPABASE_ANON_KEY in neuralops/app.env -- and the web app it is used with
# must point its NEXT_PUBLIC_SUPABASE_* at the same project, or every token
# is rejected as "not issued by this server's identity project".
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://xgfsxikypxjhqlutiepw.supabase.co").rstrip("/")
SUPABASE_JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
SUPABASE_JWT_ISSUER = f"{SUPABASE_URL}/auth/v1"
SUPABASE_JWT_AUDIENCE = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
# Optional. The project's service_role key: when set, invitations also send
# the invitee an email through Supabase's admin invite API (see
# workspace/services.py:_send_invite_email). Only ever set it on a server
# whose identity project you control -- it is a full-admin key.
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# =========================================================
# NeuralOps
# =========================================================

NEURALOPS_INSTALL_TOKEN = os.getenv("NEURALOPS_INSTALL_TOKEN", "")
NEURALOPS_SERVER_URL = os.getenv("NEURALOPS_SERVER_URL", "")  # public URL of this server
# Self-host version check (#170) -- FAT_VERSION for the fat profile, "dev"
# for the dev profile (set in docker-compose.yaml). Surfaced in
# GET /api/v1/auth/verify/ so the frontend can flag an out-of-date server.
NEURALOPS_VERSION = os.getenv("NEURALOPS_VERSION", "unknown")
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
# Field Encryption — API keys stored encrypted at rest
# =========================================================
# Generate a key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Store in .env as FIELD_ENCRYPTION_KEY=<generated-key>
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "")

# =========================================================
# Centrifugo — Real-time pub/sub
# =========================================================

CENTRIFUGO_API_URL = os.getenv("CENTRIFUGO_API_URL", "")   # e.g. http://realtime:8000/api
CENTRIFUGO_API_KEY = os.getenv("CENTRIFUGO_API_KEY", "")
CENTRIFUGO_HMAC_SECRET = os.getenv("CENTRIFUGO_HMAC_SECRET", "")

# =========================================================
# Internal service communication
# =========================================================

NEXUS_AI_URL = os.getenv("NEXUS_AI_URL", "")          # e.g. http://nexus-ai:8000
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")  # shared secret with nexus-ai

# =========================================================
# pydantic-ai capability template
# =========================================================
# The starting JSON handed to a user creating an INTERNAL MCPServer row
# (is_internal=True). Keys are NativePydanticAICapabilities members from
# modules/nexus-ai/apps/schemas/trigger.py; values are the field defaults of
# each capability's argument model.
#
# MCP is deliberately ABSENT. That capability is what an EXTERNAL server
# becomes -- nexus-ai builds MCPArgs(url=..., authorization_token=...) from
# the row's own url/auth fields at trigger time -- so it is never something
# anyone configures by hand here.
#
# {} means nexus-ai does not accept arguments for that capability yet: most
# of the argument models in trigger.py are still bare `...` stubs. The keys
# are listed anyway so the full menu of what pydantic-ai offers is visible.
#
# nucleus NEVER interprets this. It seeds the field on create, then stores
# and forwards whatever the user saved, verbatim. The shape belongs to
# trigger.py, and duplicating its validation rules here would just be a
# second place to get them wrong.
#
# Because nucleus cannot import from nexus-ai (separate service, venv and
# container), this is a COPY across the service boundary and can drift.
# Re-derive it whenever trigger.py's argument models change.
PROJECTS_ROOT = Path("/nexus/projects")
MCP_CAPABILITY_TEMPLATE = {
    "Filesystem": {
        "root_dir": ".",
        "allowed_patterns": [],
        "denied_patterns": [],
        "protected_patterns": [
            ".git/*", ".env", ".env.*", "*.pem", "*.key", "**/secrets*",
        ],
    },
    "Shell": {
        "cwd": ".",
        # Valid values, from trigger.py's ShellCommands enum: ls touch rm git
        # cd cat echo grep sed pwd mkdir cp mv head tail curl wget. Anything
        # outside that set is rejected by nexus-ai, not by nucleus.
        "allowed_commands": ["ls", "touch", "cat", "cd", "grep", "cp", "mkdir"],
        "denied_commands": [],
        "allow_interactive": True,
        "default_timeout": 30.0,
        "max_output_chars": 50000,
    },
    "Stack One": {},
    "Local Stack": {},
    "Web Search": {"local": "duckduckgo"},
    "Web Fetch": {"local": True},
    "X Search": {},
    # effort: minimal | low | medium | high | xhigh
    "Thinking": {"effort": "medium"},
    "Planning": {},
    "Sub Agents": {},
    "Dynamic Workflow": {},
    "Advisor": {},
    "Tool Search": {},
    "Compaction": {},
    "Memory": {},
    "Skills": {},
    "Repo Context": {},
    "Gaurdrails": {},
    "Spend Limits": {},
    "Tool Approval": {},
    "Capability Creation": {},
}

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

# django-celery-beat -- lets PersonaSchedule rows (via services.py) create/edit
# PeriodicTask rows at runtime and have Celery Beat actually pick them up from
# the DB, instead of Celery's default static file-based schedule.
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# =========================================================
# Logging -- console (still captured by `docker logs`/stdout redirection)
# plus a rotating file, so logs are readable straight off disk too, e.g.
# via a mounted volume on the FAT image (see Fat-Docker/). LOG_DIR
# defaults to BASE_DIR/logs; the directory is created here since Django's
# file handler doesn't create missing directories itself.
# =========================================================
LOG_DIR = Path(os.getenv("LOG_DIR", str(BASE_DIR / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} — {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "nucleus.log"),
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": os.getenv("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": os.getenv("LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}
