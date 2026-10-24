from decimal import Decimal
import json
import tempfile

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from analysis.engines.open_sage import (
    OPEN_SAGE_ENGINE,
    OPEN_SAGE_VERSION,
    OpenSageEngine,
)
from analysis.models import MatchAnalysis
from analysis.services.game_processor import process_game_analysis, prepare_game_analysis
from analysis.services.player_summary import (
    update_player_match_summary,
)
from analysis.services.processing_lease import (
    LeaseLost, ProcessingHeartbeat, claim_analysis,
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
    try:
        token = claim_analysis(match_analysis)
    except LeaseLost as exc:
        raise MatchProcessingError(str(exc)) from exc
    match_analysis.refresh_from_db()
    using = match_analysis._state.db
    owned = MatchAnalysis.objects.using(using).filter(
        pk=match_analysis.pk, status=MatchAnalysis.Status.PROCESSING, processing_token=token,
    )

    try:
        with ProcessingHeartbeat(match_analysis.pk, token, using=using) as heartbeat:
            engine = OpenSageEngine(eval_level=match_analysis.eval_level)
            # Engine calls can take minutes. Keep them outside the transaction
            # so SQLite's writer lock does not block scopes or heartbeats. A
            # temporary spool retains one prepared game's data in memory.
            with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as prepared:
                game_ids = list(match_analysis.games.order_by("game_number").values_list("pk", flat=True))
                if not game_ids:
                    raise MatchProcessingError("Match analysis contains no games.")
                for game_id in game_ids:
                    heartbeat.check()
                    game = match_analysis.games.get(pk=game_id)
                    data = prepare_game_analysis(game_analysis=game, engine=engine)
                    json.dump({"game_id": str(game_id), "analysis": data}, prepared, cls=DjangoJSONEncoder)
                    prepared.write("\n")
                    del data, game
                prepared.seek(0)
                heartbeat.check()
                with transaction.atomic(using=using):
                    _process_owned_match(match_analysis, prepared, owned, heartbeat)
        match_analysis.refresh_from_db()
        return match_analysis

    except Exception as exc:
        # A reclaimed worker must not overwrite its replacement's state.
        owned.update(
            status=MatchAnalysis.Status.FAILED, failed_at=timezone.now(),
            completed_at=None, error_message=str(exc), updated_at=timezone.now(),
            processing_token=None, lease_expires_at=None,
        )
        if isinstance(exc, LeaseLost):
            raise MatchProcessingError(str(exc)) from exc
        raise


def _process_owned_match(match_analysis, prepared, owned, heartbeat):
    # Every derived write stays in the caller's atomic transaction. The final
    # conditional update fences decisions, luck and player summaries together.
    heartbeat.check()
    game_results = []
    for line in prepared:
        heartbeat.check()
        data = json.loads(line)
        game_analysis = match_analysis.games.get(pk=data["game_id"])
        result = process_game_analysis(game_analysis=game_analysis, prepared=data["analysis"])
        game_results.append({
            "game_id": str(game_analysis.id),
            "source_game_id": game_analysis.source_game_id,
            "game_number": game_analysis.game_number,
            "checker_decisions": len(result["checker_decisions"]),
            "cube_decisions": len(result["cube_decisions"]),
            "decisions_created": result["decisions_created"],
        })

    player_summaries = {
        player.color: _json_safe(update_player_match_summary(player))
        for player in match_analysis.players.all()
    }
    match_analysis.raw_response = {
        "eval_level": match_analysis.eval_level,
        "games": game_results,
        "games_analyzed": len(game_results),
        "decisions_analyzed": sum(game["decisions_created"] for game in game_results),
        "player_summaries": player_summaries,
    }
    heartbeat.check()
    if not owned.update(
        raw_response=match_analysis.raw_response,
        engine=OPEN_SAGE_ENGINE, engine_version=OPEN_SAGE_VERSION,
        status=MatchAnalysis.Status.COMPLETED, completed_at=timezone.now(),
        updated_at=timezone.now(), processing_token=None, lease_expires_at=None,
    ):
        raise LeaseLost("Match analysis ownership was replaced.")
