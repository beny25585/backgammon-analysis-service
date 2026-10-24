"""Durable claims and independent heartbeats for the database-backed worker."""
from datetime import timedelta
import logging
import threading
import uuid

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, OperationalError, connections
from django.db.models import Q
from django.utils import timezone

from analysis.models import MatchAnalysis

logger = logging.getLogger(__name__)


class LeaseLost(ValueError):
    pass


def lease_seconds():
    return max(30, int(getattr(settings, "ANALYSIS_LEASE_SECONDS", 300)))


def expired_processing(now=None):
    now = now or timezone.now()
    # Legacy processing rows have no lease. Give a recently started old worker
    # the normal lease window instead of treating every deployment as a crash.
    legacy = Q(lease_expires_at__isnull=True) & (
        Q(started_at__isnull=True) | Q(started_at__lte=now - timedelta(seconds=lease_seconds()))
    )
    return Q(status=MatchAnalysis.Status.PROCESSING) & (Q(lease_expires_at__lte=now) | legacy)


def claim_analysis(match):
    now = timezone.now()
    token = uuid.uuid4()
    using = match._state.db or DEFAULT_DB_ALIAS
    eligible = ~Q(status=MatchAnalysis.Status.PROCESSING) | expired_processing(now)
    changed = MatchAnalysis.objects.using(using).filter(
        eligible, pk=match.pk, updated_at=match.updated_at,
    ).update(
        status=MatchAnalysis.Status.PROCESSING, processing_token=token,
        lease_expires_at=now + timedelta(seconds=lease_seconds()),
        started_at=now, updated_at=now, completed_at=None, failed_at=None,
        error_message="",
    )
    if not changed:
        raise LeaseLost("Match analysis is already processing or was changed.")
    return token


def renew_analysis(match_id, token, *, using=DEFAULT_DB_ALIAS):
    return MatchAnalysis.objects.using(using).filter(
        pk=match_id, status=MatchAnalysis.Status.PROCESSING, processing_token=token,
    ).update(lease_expires_at=timezone.now() + timedelta(seconds=lease_seconds()))


class ProcessingHeartbeat:
    """Use a thread-local connection; never share the processing transaction.

    Engine evaluation holds no write transaction. SQLite can briefly serialize
    this renewal behind final persistence; a lock error alone is not proof of
    lost ownership. The final token update fences all derived writes together.
    """

    def __init__(self, match_id, token, *, using=DEFAULT_DB_ALIAS):
        self.match_id, self.token, self.using = match_id, token, using
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread = threading.Thread(target=self._run, name="analysis-heartbeat", daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._stop.set()
        self._thread.join(timeout=5)

    def check(self):
        if self._lost.is_set():
            raise LeaseLost("Match analysis ownership was replaced.")

    def _run(self):
        connection = connections[self.using]
        interval = min(30, lease_seconds() / 3)
        try:
            while not self._stop.wait(interval):
                try:
                    changed = renew_analysis(self.match_id, self.token, using=self.using)
                    if not changed:
                        self._lost.set()
                        return
                except OperationalError:
                    # Reclamation and the final token update, rather than a
                    # transient connection/lock error, decide who may commit.
                    logger.warning("event=analysis_heartbeat_deferred match=%s", self.match_id)
                    connection.close()
        finally:
            connection.close()
