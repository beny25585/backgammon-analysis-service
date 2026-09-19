from decimal import Decimal

from django.db import transaction

from analysis.engines.open_sage import OpenSageEngine
from analysis.models import (
    PlayerGameAnalysis,
    RollLuckAnalysis,
)
from analysis.services.luck_analysis import (
    analyze_roll_luck,
)
from analysis.services.luck_stream import (
    extract_luck_rolls,
)


class LuckProcessingError(ValueError):
    pass


def _decimal(value):
    return Decimal(str(value))


@transaction.atomic
def process_game_luck(
    *,
    game_analysis,
    engine=None,
):
    if engine is None:
        engine = OpenSageEngine()

    player_games = {
        player_game.match_player_analysis.color: player_game
        for player_game in (
            PlayerGameAnalysis.objects
            .filter(
                game_analysis=game_analysis
            )
            .select_related(
                "match_player_analysis"
            )
        )
    }

    if "white" not in player_games:
        raise LuckProcessingError(
            "Missing white PlayerGameAnalysis."
        )

    if "black" not in player_games:
        raise LuckProcessingError(
            "Missing black PlayerGameAnalysis."
        )

    rolls = extract_luck_rolls(
        game_analysis
    )

    # Reprocessing must not duplicate roll records.
    RollLuckAnalysis.objects.filter(
        player_game_analysis__game_analysis=(
            game_analysis
        )
    ).delete()

    created = []

    luck_totals = {
        "white": Decimal("0"),
        "black": Decimal("0"),
    }

    roll_counts = {
        "white": 0,
        "black": 0,
    }

    for roll in rolls:
        analysis = analyze_roll_luck(
            game_analysis=game_analysis,
            roll=roll,
            engine=engine,
        )

        player = analysis["player"]

        if player not in player_games:
            raise LuckProcessingError(
                f"Missing PlayerGameAnalysis "
                f"for {player!r}."
            )

        luck_value = _decimal(
            analysis["luck"]
        )

        record = RollLuckAnalysis.objects.create(
            player_game_analysis=(
                player_games[player]
            ),
            source_event_sequence=(
                analysis[
                    "source_event_sequence"
                ]
            ),
            dice=analysis["dice"],
            is_opening_roll=analysis[
                "is_opening_roll"
            ],
            luck=luck_value,
            actual_equity=_decimal(
                analysis["actual_equity"]
            ),
            average_equity=_decimal(
                analysis["average_equity"]
            ),
            ply=analysis["ply"],
            level_label=analysis[
                "level_label"
            ],
            position_snapshot=analysis[
                "position_snapshot"
            ],
            raw_analysis=analysis[
                "raw_analysis"
            ],
        )

        created.append(record)

        luck_totals[player] += luck_value
        roll_counts[player] += 1

    for color in ("white", "black"):
        player_game = player_games[color]

        player_game.luck = (
            luck_totals[color]
        )

        player_game.save(
            update_fields=[
                "luck",
                "updated_at",
            ]
        )

    return {
        "rolls": created,
        "rolls_analyzed": len(created),

        "white": {
            "luck": luck_totals["white"],
            "rolls": roll_counts["white"],
        },

        "black": {
            "luck": luck_totals["black"],
            "rolls": roll_counts["black"],
        },
    }
