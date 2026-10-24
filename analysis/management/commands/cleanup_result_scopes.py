"""Optional bounded cleanup for installations that run HTTP without a worker."""
from django.core.management.base import BaseCommand

from analysis.api.result_scopes import cleanup_expired_scopes


class Command(BaseCommand):
    help = "Delete one batch of at most 25 expired analysis access scopes."

    def handle(self, *args, **options):
        self.stdout.write(str(cleanup_expired_scopes()))
