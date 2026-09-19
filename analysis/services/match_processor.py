from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from analysis.engines.open_sage import (
    OPEN_SAGE_ENGINE,
    OPEN_SAGE_VERSION,
    OpenSageEngine,
)
from analysis.models import MatchAnalysis
from analysis.services.game_processor import process_game_analysis
from analysis.services.player_summary import (
    update_player_match_summary,
)


class MatchProcessingError(ValueError):
    pass


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, dict):
        return {
            key: _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            _json_safe(item)
            for item in value
        ]

    return value


def process_match_analysis(*, match_analysis):
    if match_analysis.status == MatchAnalysis.Status.PROCESSING:
        raise MatchProcessingError(
            "Match analysis is already processing."
        )

    claimed = MatchAnalysis.objects.filter(pk=match_analysis.pk, updated_at=match_analysis.updated_at).exclude(
        status=MatchAnalysis.Status.PROCESSING
    ).update(status=MatchAnalysis.Status.PROCESSING)
    if not claimed:
        raise MatchProcessingError("Match analysis is already processing.")
    match_analysis.refresh_from_db()

    match_analysis.status = MatchAnalysis.Status.PROCESSING
    match_analysis.engine = OPEN_SAGE_ENGINE
    match_analysis.engine_version = OPEN_SAGE_VERSION
    match_analysis.started_at = timezone.now()
    match_analysis.completed_at = None
    match_analysis.failed_at = None
    match_analysis.error_message = ""

    match_analysis.save(
        update_fields=[
            "status",
            "engine",
            "engine_version",
            "started_at",
            "completed_at",
            "failed_at",
            "error_message",
            "updated_at",
        ]
    )

    try:
        engine = OpenSageEngine(eval_level=match_analysis.eval_level)
        with transaction.atomic():
            games = match_analysis.games.order_by(
                "game_number"
            )

            if not games.exists():
                raise MatchProcessingError(
                    "Match analysis contains no games."
                )

            game_results = []

            for game_analysis in games:
                result = process_game_analysis(
                    game_analysis=game_analysis,
                    engine=engine,
                )

                game_results.append(
                    {
                        "game_id": str(
                            game_analysis.id
                        ),
                        "source_game_id": (
                            game_analysis.source_game_id
                        ),
                        "game_number": (
                            game_analysis.game_number
                        ),
                        "checker_decisions": len(
                            result[
                                "checker_decisions"
                            ]
                        ),
                        "cube_decisions": len(
                            result[
                                "cube_decisions"
                            ]
                        ),
                        "decisions_created": (
                            result[
                                "decisions_created"
                            ]
                        ),
                    }
                )

            player_summaries = {}

            match_players = (
                match_analysis.players.all()
            )

            for player_match_analysis in match_players:
                summary = (
                    update_player_match_summary(
                        player_match_analysis
                    )
                )

                player_summaries[
                    player_match_analysis.color
                ] = _json_safe(summary)

            total_decisions = sum(
                game["decisions_created"]
                for game in game_results
            )

            match_analysis.raw_response = {
                "eval_level": match_analysis.eval_level,
                "games": game_results,
                "games_analyzed": len(
                    game_results
                ),
                "decisions_analyzed": (
                    total_decisions
                ),
                "player_summaries": (
                    player_summaries
                ),
            }

            match_analysis.status = (
                MatchAnalysis.Status.COMPLETED
            )
            match_analysis.completed_at = (
                timezone.now()
            )

            match_analysis.save(
                update_fields=[
                    "raw_response",
                    "status",
                    "completed_at",
                    "updated_at",
                ]
            )

        return match_analysis

    except Exception as exc:
        match_analysis.status = (
            MatchAnalysis.Status.FAILED
        )
        match_analysis.failed_at = timezone.now()
        match_analysis.completed_at = None
        match_analysis.error_message = str(exc)

        match_analysis.save(
            update_fields=[
                "status",
                "failed_at",
                "completed_at",
                "error_message",
                "updated_at",
            ]
        )

        raise
