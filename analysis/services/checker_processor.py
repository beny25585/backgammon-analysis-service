from decimal import Decimal

from django.db import transaction

from analysis.models import DecisionAnalysis
from analysis.services.checker_analysis import analyze_checker_decision
from analysis.services.decision_stream import extract_checker_decisions


class CheckerProcessingError(ValueError):
    pass


def _decimal(value):
    if value is None:
        return None
    return Decimal(str(value))


@transaction.atomic
def process_game_checker_decisions(
    *,
    game_analysis,
    engine=None,
):
    """
    Extract, analyze and persist all checker-play decisions for one game.

    Safe to run again:
    existing checker decisions for this game are replaced atomically.
    Cube decisions and other future decision types are left untouched.
    """

    player_game_analyses = {
        player_game.match_player_analysis.color: player_game
        for player_game in game_analysis.players.select_related(
            "match_player_analysis"
        ).all()
    }

    if "white" not in player_game_analyses:
        raise CheckerProcessingError(
            "Game is missing white PlayerGameAnalysis."
        )

    if "black" not in player_game_analyses:
        raise CheckerProcessingError(
            "Game is missing black PlayerGameAnalysis."
        )

    extracted_decisions = extract_checker_decisions(game_analysis)

    # Re-processing the same game must not create duplicate checker decisions.
    DecisionAnalysis.objects.filter(
        player_game_analysis__game_analysis=game_analysis,
        decision_type=DecisionAnalysis.DecisionType.CHECKER_MOVE,
    ).delete()

    created = []

    for decision in extracted_decisions:
        analysis = analyze_checker_decision(
            game_analysis=game_analysis,
            decision=decision,
            engine=engine,
        )

        player = analysis["player"]

        try:
            player_game_analysis = player_game_analyses[player]
        except KeyError as exc:
            raise CheckerProcessingError(
                f"No PlayerGameAnalysis for {player!r}."
            ) from exc

        source_event_sequence = analysis.get(
            "source_event_sequence"
        )

        if source_event_sequence is None:
            raise CheckerProcessingError(
                "Checker decision is missing source_event_sequence."
            )

        persisted = DecisionAnalysis.objects.create(
            player_game_analysis=player_game_analysis,

            # Use the original GameEvent sequence.
            # This keeps checker/cube decisions on the same timeline later.
            sequence_number=int(source_event_sequence),
            source_event_sequence=int(source_event_sequence),

            decision_type=(
                DecisionAnalysis.DecisionType.CHECKER_MOVE
            ),

            dice=analysis["dice"],

            played_action=analysis.get("played_action"),
            best_action=analysis.get("best_action"),
            alternatives=analysis.get("alternatives") or [],

            played_equity=_decimal(
                analysis.get("played_equity")
            ),
            best_equity=_decimal(
                analysis.get("best_equity")
            ),
            equity_loss=_decimal(
                analysis.get("equity_loss")
            ),

            classification=(
                DecisionAnalysis.Classification.UNCLASSIFIED
            ),

            position_snapshot=(
                analysis.get("position_snapshot") or {}
            ),

            raw_analysis=(
                analysis.get("raw_analysis") or {}
            ),
        )

        created.append(persisted)

    return created
