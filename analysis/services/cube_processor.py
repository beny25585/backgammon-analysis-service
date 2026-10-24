from decimal import Decimal

from django.db import transaction

from analysis.models import DecisionAnalysis
from analysis.services.cube_analysis import analyze_cube_decision
from analysis.services.classification import classify_decision
from analysis.services.decision_stream import extract_cube_decisions


class CubeProcessingError(ValueError):
    pass


def _decimal(value):
    if value is None:
        return None
    return Decimal(str(value))


def _decision_type(value):
    mapping = {
        "no_double": DecisionAnalysis.DecisionType.NO_DOUBLE,
        "double": DecisionAnalysis.DecisionType.DOUBLE,
        "redouble": DecisionAnalysis.DecisionType.REDOUBLE,
        "take": DecisionAnalysis.DecisionType.TAKE,
        "pass": DecisionAnalysis.DecisionType.PASS,
    }

    try:
        return mapping[value]
    except KeyError as exc:
        raise CubeProcessingError(
            f"Unsupported cube decision type: {value!r}"
        ) from exc


def _alternatives(value):
    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        return [
            {
                "action": action,
                "equity": equity,
            }
            for action, equity in value.items()
        ]

    return []


def prepare_game_cube_decisions(*, game_analysis, engine):
    return [analyze_cube_decision(game_analysis=game_analysis, decision=decision, engine=engine)
            for decision in extract_cube_decisions(game_analysis)]


@transaction.atomic
def process_game_cube_decisions(
    *,
    game_analysis,
    engine=None,
    prepared=None,
):
    player_game_analyses = {
        player_game.match_player_analysis.color: player_game
        for player_game in game_analysis.players.select_related(
            "match_player_analysis"
        ).all()
    }

    if "white" not in player_game_analyses:
        raise CubeProcessingError(
            "Game is missing white PlayerGameAnalysis."
        )

    if "black" not in player_game_analyses:
        raise CubeProcessingError(
            "Game is missing black PlayerGameAnalysis."
        )

    analyses = prepared if prepared is not None else prepare_game_cube_decisions(
        game_analysis=game_analysis, engine=engine,
    )

    # Re-processing must replace only cube decisions.
    DecisionAnalysis.objects.filter(
        player_game_analysis__game_analysis=game_analysis,
        decision_type__in=[
            DecisionAnalysis.DecisionType.NO_DOUBLE,
            DecisionAnalysis.DecisionType.DOUBLE,
            DecisionAnalysis.DecisionType.REDOUBLE,
            DecisionAnalysis.DecisionType.TAKE,
            DecisionAnalysis.DecisionType.PASS,
        ],
    ).delete()

    created = []

    for analysis in analyses:
        player = analysis["player"]

        try:
            player_game_analysis = (
                player_game_analyses[player]
            )
        except KeyError as exc:
            raise CubeProcessingError(
                f"No PlayerGameAnalysis for {player!r}."
            ) from exc

        source_sequence = analysis.get(
            "source_event_sequence"
        )

        if source_sequence is None:
            raise CubeProcessingError(
                "Cube decision is missing "
                "source_event_sequence."
            )

        persisted = DecisionAnalysis(
            player_game_analysis=player_game_analysis,

            sequence_number=int(source_sequence),
            source_event_sequence=int(source_sequence),

            decision_type=_decision_type(
                analysis["decision_type"]
            ),

            dice=[],

            played_action=analysis.get(
                "played_action"
            ),
            best_action=analysis.get(
                "best_action"
            ),

            alternatives=_alternatives(
                analysis.get("alternatives")
            ),

            played_equity=_decimal(
                analysis.get("played_equity")
            ),
            best_equity=_decimal(
                analysis.get("best_equity")
            ),
            equity_loss=_decimal(
                analysis.get("equity_loss")
            ),


            position_snapshot=(
                analysis.get("position_snapshot")
                or {}
            ),

            raw_analysis=(
                analysis.get("raw_analysis")
                or {}
            ),
        )

        # Classify the six-decimal loss that the model will actually store.
        if persisted.equity_loss is not None and persisted.equity_loss.is_finite():
            persisted.equity_loss = persisted.equity_loss.quantize(Decimal("0.000001"))
        persisted.classification = classify_decision(persisted)
        persisted.save()
        created.append(persisted)

    return created
