"""Settings for the isolated Gunicorn service behind the deployment Nginx."""
from .settings import *  # noqa: F403

DEBUG = False
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("development-only"):
    raise ImproperlyConfigured("Set a unique DJANGO_SECRET_KEY of at least 50 characters.")
STATIC_URL = "/static/"
STATIC_ROOT = Path(os.environ["STATIC_ROOT"])
MEDIA_ROOT = Path(os.environ["MEDIA_ROOT"])
HTTPS_ENABLED = os.getenv("DJANGO_PUBLIC_SCHEME", "http") == "https"
SESSION_COOKIE_SECURE = HTTPS_ENABLED
CSRF_COOKIE_SECURE = HTTPS_ENABLED
SECURE_SSL_REDIRECT = HTTPS_ENABLED
# Only Nginx reaches this service; it replaces the forwarded scheme with a fixed value.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
