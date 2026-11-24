import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-development-key-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [item.strip() for item in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if item.strip()]
CSRF_TRUSTED_ORIGINS = [item.strip() for item in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if item.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "runtwin.athletes",
    "runtwin.activities",
    "runtwin.reporting",
    "runtwin.web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ]},
    }
]
WSGI_APPLICATION = "config.wsgi.application"

if os.getenv("DATABASE_URL"):
    from urllib.parse import urlparse

    parsed = urlparse(os.environ["DATABASE_URL"])
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username,
        "PASSWORD": parsed.password,
        "HOST": parsed.hostname,
        "PORT": parsed.port or 5432,
        "CONN_MAX_AGE": 60,
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

LANGUAGE_CODE = "zh-hant"
TIME_ZONE = "Asia/Taipei"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {"staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/admin/login/"
REST_FRAMEWORK = {"DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"]}
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = os.getenv("DJANGO_SECURE_COOKIES", "0") == "1"
CSRF_COOKIE_SECURE = os.getenv("DJANGO_SECURE_COOKIES", "0") == "1"
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "0") == "1"
if os.getenv("DJANGO_BEHIND_HTTPS_PROXY", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0

DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
RUNTWIN_PROVIDER = os.getenv("RUNTWIN_PROVIDER", "snapshot")
# Optional LLM analysis: "anthropic" or "openai". Empty means deterministic analysis only.
RUNTWIN_AI_PROVIDER = os.getenv("RUNTWIN_AI_PROVIDER", "").strip().lower()
RUNTWIN_AI_MODEL = os.getenv("RUNTWIN_AI_MODEL", "")
RUNTWIN_AI_EFFORT = os.getenv("RUNTWIN_AI_EFFORT", "medium")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
RUNTWIN_ANALYSIS_LABEL = os.getenv("RUNTWIN_ANALYSIS_LABEL", "RunTwin analysis")
RUNTWIN_LEGACY_ANALYSIS_LABELS = [item.strip() for item in os.getenv("RUNTWIN_LEGACY_ANALYSIS_LABELS", "").split(",") if item.strip()]
RUNTWIN_EXPORT_DIR = Path(os.getenv("RUNTWIN_EXPORT_DIR", BASE_DIR / "runtime" / "exports"))
RUNTWIN_GARMIN_ENABLED = os.getenv("RUNTWIN_GARMIN_ENABLED", "0") == "1"
RUNTWIN_GARMIN_TOKEN_DIR = os.path.expanduser(os.getenv("RUNTWIN_GARMIN_TOKEN_DIR", "~/.garminconnect"))
STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID", "")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")
STRAVA_REFRESH_TOKEN = os.getenv("STRAVA_REFRESH_TOKEN", "")
STRAVA_TOKEN_FILE = Path(os.getenv("STRAVA_TOKEN_FILE", BASE_DIR / "runtime" / "strava-token.json"))
STRAVA_API_BASE_URL = os.getenv("STRAVA_API_BASE_URL", "https://www.strava.com/api/v3")
STRAVA_WEBHOOK_PATH_TOKEN = os.getenv("STRAVA_WEBHOOK_PATH_TOKEN", "not-configured")
STRAVA_WEBHOOK_VERIFY_TOKEN = os.getenv("STRAVA_WEBHOOK_VERIFY_TOKEN", "")
STRAVA_WEBHOOK_SIGNING_SECRET = os.getenv("STRAVA_WEBHOOK_SIGNING_SECRET", "")
STRAVA_WEBHOOK_REQUIRE_SIGNATURE = os.getenv("STRAVA_WEBHOOK_REQUIRE_SIGNATURE", "0") == "1"
STRAVA_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS = int(os.getenv("STRAVA_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS", "300"))
STRAVA_WEBHOOK_CALLBACK_URL = os.getenv("STRAVA_WEBHOOK_CALLBACK_URL", "")
STRAVA_WEBHOOK_SUBSCRIPTION_ID = os.getenv("STRAVA_WEBHOOK_SUBSCRIPTION_ID", "")
STRAVA_ATHLETE_ID = os.getenv("STRAVA_ATHLETE_ID", "")
STRAVA_WEBHOOK_POLL_SECONDS = int(os.getenv("STRAVA_WEBHOOK_POLL_SECONDS", "10"))
STRAVA_WEBHOOK_MAX_ATTEMPTS = int(os.getenv("STRAVA_WEBHOOK_MAX_ATTEMPTS", "3"))
STRAVA_WEBHOOK_PROCESSING_TIMEOUT_SECONDS = int(os.getenv("STRAVA_WEBHOOK_PROCESSING_TIMEOUT_SECONDS", "1800"))
STRAVA_RECONCILE_INTERVAL_SECONDS = int(os.getenv("STRAVA_RECONCILE_INTERVAL_SECONDS", "3600"))
STRAVA_RECONCILE_DAYS = int(os.getenv("STRAVA_RECONCILE_DAYS", "14"))
