"""
Django settings for core project.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# =========================================================
# Posture (Step 4, docs/NUCLEUS-REVAMP.md) — safe by default.
# DEBUG is OFF unless the environment says otherwise (the dev-profile
# compose services set DEBUG=true). A non-debug boot with no SECRET_KEY
# refuses to start, loudly, instead of running every deployment on one
# shared, published signing key — local sign-in tokens
# (authn/local_auth.py) and Django's own session/CSRF machinery are
# signed with it. init-secrets generates it (see neuralops/entrypoint.sh);
# existing deployments add one SECRET_KEY=... line to neuralops/secrets.env.
# =========================================================
DEBUG = _env_bool("DEBUG", False)

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        # Dev-only convenience — never reachable with DEBUG off.
        SECRET_KEY = 'django-insecure-zj(1$&@l(309znsv2&p3h%8hy571$2+!yh+niu)h3x!btilq36'
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY is not set. Generate this deployment's secrets first:\n"
            "  docker run --rm <neuralops image> init-secrets > neuralops/secrets.env\n"
            "(or append one SECRET_KEY=<long random string> line to your existing "
            "neuralops/secrets.env — don't regenerate the file, that would replace "
            "POSTGRES_PASSWORD and the other live secrets), then start again. "
            "Set DEBUG=true only for development."
        )
# The public hook endpoint (scheduling/hooks_api.py) accepts a body from anyone
# who has a token, and Django parses it before our code runs. 64 KB is well over
# the 4 KB of text + 32 KB of data a fire may carry, and far under the 2.5 MB
# default an unauthenticated caller could otherwise make this process parse.
DATA_UPLOAD_MAX_MEMORY_SIZE = 64 * 1024
# Self-hosted servers are reached by LAN addresses, Tailscale names and
# tunnels nobody can predict, and auth is bearer-token (the Host header never
# mints links or cookies here) — so the default stays open, and a deployment
# that wants to pin names sets ALLOWED_HOSTS=a.example,b.example in app.env.
_hosts = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
ALLOWED_HOSTS = _hosts or ["*"]

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
    'gateway',
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
# CORS — the hosted web app may run on any origin and talks to any
# self-hosted server with a bearer token (no cookies ride on it), so the
# default stays open — closing it would break the product's own sign-in.
# A deployment that wants to pin origins sets
# CORS_ALLOWED_ORIGINS=https://app.example,https://other.example in app.env.
# =========================================================
_cors_origins = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    CORS_ALLOWED_ORIGINS = _cors_origins
    CORS_ALLOW_ALL_ORIGINS = False
else:
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

# Overridable so a deployment can verify sign-ins against its own Supabase
# project (the web app must point at the same one); JWKS and issuer follow it.
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://xgfsxikypxjhqlutiepw.supabase.co").rstrip("/")
SUPABASE_JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
SUPABASE_JWT_ISSUER = f"{SUPABASE_URL}/auth/v1"
SUPABASE_JWT_AUDIENCE = "authenticated"
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
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

# Step 4 — local (offline) sign-in: a user who set a password in their
# profile can sign in without Supabase. Tokens are HS256, signed with this
# server's SECRET_KEY — see authn/local_auth.py. Turn off with
# LOCAL_LOGIN_ENABLED=false to make Supabase the only door.
LOCAL_LOGIN_ENABLED = _env_bool("LOCAL_LOGIN_ENABLED", True)
LOCAL_TOKEN_HOURS = int(os.getenv("LOCAL_TOKEN_HOURS", "24"))

# Step 6 — the MCP gateway (/api/v1/mcp/): this server usable as a tool, from
# outside (Claude Desktop, Cursor — personal tokens) and inside (personas —
# internal key + the triggering user's id). GATEWAY_ENABLED=false closes the
# whole door. ASK_TIMEOUT is how long ask_persona waits for a reply before
# answering "still working — check the topic" (the reply keeps running).
GATEWAY_ENABLED = _env_bool("GATEWAY_ENABLED", True)
GATEWAY_ASK_TIMEOUT_SECONDS = int(os.getenv("GATEWAY_ASK_TIMEOUT_SECONDS", "180"))

# Step 6 ruling 5 — the phone-home: ONE total, on app open + close, to a
# Supabase edge function (public — every customer's install must reach it;
# never a private/tailscale address). Fails silently offline. See
# core/phone_home.py for the function's contract.
NEURALOPS_PHONE_HOME_URL = os.getenv(
    "NEURALOPS_PHONE_HOME_URL",
    f"{SUPABASE_URL}/functions/v1/phone-home",
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
    "filesystem": {
        "root_dir": ".",
        "allowed_patterns": [],
        "denied_patterns": [],
        "protected_patterns": [
            ".git/*", ".env", ".env.*", "*.pem", "*.key", "**/secrets*",
        ],
    },
    "shell": {
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
    "stack_one": {},
    "local_stack": {},
    "web_search": {"local": "duckduckgo"},
    "web_fetch": {"local": True},
    "x_search": {},
    # effort: minimal | low | medium | high | xhigh
    "thinking": {"effort": "medium"},
    "planning": {},
    "sub_agents": {},
    "dynamic_workflow": {},
    "advisor": {},
    "tool_search": {},
    "compaction": {},
    "memory": {},
    "skills": {},
    "repo_context": {},
    "gaurdrails": {},
    "spend_limits": {},
    "tool_approval": {},
    "capability_creation": {},
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
# Prices (Step 1, docs/NUCLEUS-REVAMP.md) — the catalog refresh.
# Money is ALWAYS presented as estimated ("prices not confirmed").
# Offline installs: the fetch fails silently; the last-known catalog or the
# admin's per-model overrides keep working. Set MODEL_PRICES_URL="" to turn
# the fetch off entirely.
# =========================================================
MODEL_PRICES_URL = os.getenv(
    "MODEL_PRICES_URL",
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json",
)
# DatabaseScheduler syncs these static entries into PeriodicTask rows on beat
# start — so this coexists with the runtime PersonaSchedule rows.
CELERY_BEAT_SCHEDULE = {
    "refresh-model-prices-daily": {
        "task": "intelligence.tasks.refresh_model_prices",
        "schedule": 60 * 60 * 24,
    },
    # Step 3 (handoff change 9): a paused reply older than 24h is resumed
    # with deny/no-answer so it completes instead of hanging forever.
    "expire-paused-runs-hourly": {
        "task": "chat.tasks.expire_paused_runs",
        "schedule": 60 * 60,
    },
}

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
