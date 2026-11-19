import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .env import load_env_file

BASE_DIR = Path(__file__).resolve().parent.parent
load_env_file(BASE_DIR / ".env")

_INSECURE_SECRET_KEYS = {
    "",
    "local-development-keycafe-tableau",
    "replace-with-a-random-secret",
}
_RUNNING_TESTS = len(sys.argv) > 1 and sys.argv[1] == "test"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _resolve_secret_key(debug: bool, running_tests: bool) -> str:
    secret_key = os.environ.get("DJANGO_SECRET_KEY", "").strip()
    if not debug and not running_tests and secret_key in _INSECURE_SECRET_KEYS:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set to a unique secret when DJANGO_DEBUG is false."
        )
    return secret_key or "local-development-keycafe-tableau"


DEBUG = _env_bool("DJANGO_DEBUG", False)
SECRET_KEY = _resolve_secret_key(DEBUG, _RUNNING_TESTS)
ALLOWED_HOSTS = _parse_csv(os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost"))

INSTALLED_APPS = [
    "keycafe_api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "keycafe_tableau.urls"
WSGI_APPLICATION = "keycafe_tableau.wsgi.application"

LANGUAGE_CODE = "de"
STATIC_URL = "/assets/"
STATIC_ROOT = BASE_DIR / "frontend" / "dist" / "assets"
WHITENOISE_USE_FINDERS = False

X_FRAME_OPTIONS = "DENY"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = _env_bool("DJANGO_CSRF_COOKIE_SECURE", not DEBUG)
CSRF_TRUSTED_ORIGINS = _parse_csv(os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", ""))

TABLEAU_GROUPS_DB = os.environ.get("TABLEAU_GROUPS_DB", str(BASE_DIR / "data" / "groups.sqlite3"))
TABLEAU_UPSTREAM_DB = os.environ.get("TABLEAU_UPSTREAM_DB", str(Path(TABLEAU_GROUPS_DB).with_name("upstream.sqlite3")))
KEYCAFE_CACHE_SECONDS = max(1, _env_int("KEYCAFE_CACHE_SECONDS", 60))
KEYCAFE_REQUESTS_PER_MINUTE = max(1, min(60, _env_int("KEYCAFE_REQUESTS_PER_MINUTE", 50)))
