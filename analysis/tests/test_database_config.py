from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.database import postgresql_database


class PostgreSQLConfigurationTests(SimpleTestCase):
    def connection(self, **changes):
        return {'DB_NAME': 'analysis_test', 'DB_USER': 'analysis_test',
                'DB_PASSWORD': 'config-test-password', **changes}

    def test_native_local_defaults_use_postgresql_and_explicit_credentials(self):
        database = postgresql_database(self.connection())
        self.assertEqual(database['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(database['HOST'], '127.0.0.1')
        self.assertEqual(database['PORT'], '5432')
        with self.assertRaisesMessage(ImproperlyConfigured, 'DB_NAME, DB_USER, DB_PASSWORD'):
            postgresql_database({})

    def test_docker_requires_and_preserves_its_explicit_host(self):
        database = postgresql_database(self.connection(DB_HOST='postgres', DB_PORT='55432'), require_host=True)
        self.assertEqual(database['HOST'], 'postgres')
        self.assertEqual(database['PORT'], '55432')
        with self.assertRaisesMessage(ImproperlyConfigured, 'DB_HOST'):
            postgresql_database(self.connection(), require_host=True)

    def test_non_postgresql_url_cannot_silently_override_or_fall_back(self):
        for url in ('sqlite:///ignored.sqlite3', 'mysql://user:config-test-password@localhost/db'):
            with self.subTest(scheme=url.split(':', 1)[0]), self.assertRaises(ImproperlyConfigured) as raised:
                postgresql_database(self.connection(DATABASE_URL=url))
            self.assertNotIn('config-test-password', str(raised.exception))
