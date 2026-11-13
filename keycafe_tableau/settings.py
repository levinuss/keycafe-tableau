import os
from pathlib import Path

from .env import load_env_file

BASE_DIR = Path(__file__).resolve().parent.parent
load_env_file(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "local-development-keycafe-tableau")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")

INSTALLED_APPS = [
    "keycafe_api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "keycafe_tableau.urls"
WSGI_APPLICATION = "keycafe_tableau.wsgi.application"

LANGUAGE_CODE = "de"
STATIC_URL = "/assets/"
STATIC_ROOT = BASE_DIR / "frontend" / "dist" / "assets"
WHITENOISE_USE_FINDERS = False

TABLEAU_GROUPS_DB = os.environ.get("TABLEAU_GROUPS_DB", str(BASE_DIR / "data" / "groups.sqlite3"))

CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()]

TABLEAU_UPSTREAM_DB = os.environ.get("TABLEAU_UPSTREAM_DB", str(Path(TABLEAU_GROUPS_DB).with_name("upstream.sqlite3")))
KEYCAFE_CACHE_SECONDS = max(1, int(os.environ.get("KEYCAFE_CACHE_SECONDS", "60")))
KEYCAFE_REQUESTS_PER_MINUTE = max(1, min(60, int(os.environ.get("KEYCAFE_REQUESTS_PER_MINUTE", "50"))))
