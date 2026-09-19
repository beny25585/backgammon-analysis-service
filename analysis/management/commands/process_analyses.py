"""Durable database-backed analysis worker. Run separately from the HTTP server."""
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from analysis.models import MatchAnalysis
from analysis.services.match_processor import process_match_analysis, MatchProcessingError


class Command(BaseCommand):
    help = "Process pending analyses; use --once to drain the current queue and exit."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            match = MatchAnalysis.objects.filter(status="pending").order_by("updated_at").first()
            if match is None:
                if options["once"]:
                    return
                time.sleep(2)
                continue
            try:
                process_match_analysis(match_analysis=match)
            except MatchProcessingError:
                # Another worker may have claimed this row after our read.
                continue
            except Exception as exc:
                self.stderr.write(f"Analysis {match.pk} failed: {exc}")
