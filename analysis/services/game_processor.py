from django.db import transaction

from analysis.engines.open_sage import OpenSageEngine
from analysis.services.checker_processor import (
    process_game_checker_decisions, prepare_game_checker_decisions,
)
from analysis.services.cube_processor import (
    process_game_cube_decisions, prepare_game_cube_decisions,
)
from analysis.services.luck_processor import (
    process_game_luck, prepare_game_luck,
)
from analysis.services.player_summary import (
    update_player_game_summary,
)


def prepare_game_analysis(*, game_analysis, engine):
    """Evaluate the same inputs once; defer every derived write until fencing."""
    return {
        "checker": prepare_game_checker_decisions(game_analysis=game_analysis, engine=engine),
        "cube": prepare_game_cube_decisions(game_analysis=game_analysis, engine=engine),
        "luck": prepare_game_luck(game_analysis=game_analysis, engine=engine),
    }


@transaction.atomic
def process_game_analysis(
    *,
    game_analysis,
    engine=None,
    prepared=None,
):
    if engine is None and prepared is None:
        engine = OpenSageEngine()

    checker_decisions = process_game_checker_decisions(
        game_analysis=game_analysis,
        engine=engine,
        prepared=prepared["checker"] if prepared is not None else None,
    )

    cube_decisions = process_game_cube_decisions(
        game_analysis=game_analysis,
        engine=engine,
        prepared=prepared["cube"] if prepared is not None else None,
    )

    luck_result = process_game_luck(
        game_analysis=game_analysis,
        engine=engine,
        prepared=prepared["luck"] if prepared is not None else None,
    )

    player_summaries = {}

    player_games = (
        game_analysis.players
        .select_related(
            "match_player_analysis"
        )
        .all()
    )

    for player_game_analysis in player_games:
        color = (
            player_game_analysis
            .match_player_analysis
            .color
        )

        player_summaries[color] = (
            update_player_game_summary(
                player_game_analysis
            )
        )

    return {
        "checker_decisions": checker_decisions,
        "cube_decisions": cube_decisions,

        "decisions_created": (
            len(checker_decisions)
            + len(cube_decisions)
        ),

        "luck": luck_result,

        "rolls_analyzed": (
            luck_result["rolls_analyzed"]
        ),

        "player_summaries": player_summaries,
    }
