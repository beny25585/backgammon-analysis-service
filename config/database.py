"""Local and container analysis workers both require PostgreSQL."""
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def postgresql_database(environ, *, require_host=False):
    url = environ.get('DATABASE_URL', '').strip()
    try:
        valid_scheme = not url or urlsplit(url).scheme.lower() in ('postgres', 'postgresql', 'pgsql')
    except ValueError:
        valid_scheme = False
    if not valid_scheme:
        raise ImproperlyConfigured('PostgreSQL is required; SQLite and other DATABASE_URL schemes are unsupported.')
    required = ('DB_NAME', 'DB_USER', 'DB_PASSWORD') + (('DB_HOST',) if require_host else ())
    missing = [key for key in required if not environ.get(key)]
    if missing:
        raise ImproperlyConfigured('PostgreSQL configuration requires: ' + ', '.join(missing) + '.')
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': environ['DB_NAME'],
        'USER': environ['DB_USER'],
        'PASSWORD': environ['DB_PASSWORD'],
        'HOST': environ.get('DB_HOST', '127.0.0.1'),
        'PORT': environ.get('DB_PORT', '5432'),
        'CONN_MAX_AGE': 0,
        'OPTIONS': {'connect_timeout': 5},
    }
