"""Settings for the isolated local test suite."""

from .settings import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:", "MIGRATE": True},
    }
}

SECURE_SSL_REDIRECT = False
STRAVA_ENABLED = False
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
