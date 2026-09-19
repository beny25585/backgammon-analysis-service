from decimal import Decimal

from django.db import transaction

from analysis.models import DecisionAnalysis
from analysis.services.scoring import (
    calculate_pr,
    is_blunder,
    is_scoreable_decision,
)


CHECKER_TYPES = {
    DecisionAnalysis.DecisionType.CHECKER_MOVE,
}

CUBE_TYPES = {
    DecisionAnalysis.DecisionType.NO_DOUBLE,
    DecisionAnalysis.DecisionType.DOUBLE,
    DecisionAnalysis.DecisionType.REDOUBLE,
    DecisionAnalysis.DecisionType.TAKE,
    DecisionAnalysis.DecisionType.PASS,
}


def _sum_equity_loss(decisions):
    return sum(
        (
            decision.equity_loss
            for decision in decisions
            if decision.equity_loss is not None
            and is_scoreable_decision(decision)
        ),
        Decimal("0"),
    )


def _scoreable(decisions):
    return [
        decision
        for decision in decisions
        if is_scoreable_decision(decision)
        and decision.equity_loss is not None
    ]


@transaction.atomic
def update_player_game_summary(player_game_analysis):
    decisions = list(
        player_game_analysis.decisions.all()
    )

    checker = [
        decision
        for decision in decisions
        if decision.decision_type in CHECKER_TYPES
    ]

    cube = [
        decision
        for decision in decisions
        if decision.decision_type in CUBE_TYPES
    ]

    scoreable_all = _scoreable(decisions)
    scoreable_checker = _scoreable(checker)
    scoreable_cube = _scoreable(cube)

    player_game_analysis.pr = calculate_pr(
        decisions
    )

    player_game_analysis.checker_pr = calculate_pr(
        checker
    )

    player_game_analysis.cube_pr = calculate_pr(
        cube
    )

    player_game_analysis.equity_lost = (
        _sum_equity_loss(decisions)
    )

    player_game_analysis.checker_blunders = sum(
        1
        for decision in scoreable_checker
        if is_blunder(decision)
    )

    player_game_analysis.cube_blunders = sum(
        1
        for decision in scoreable_cube
        if is_blunder(decision)
    )

    player_game_analysis.blunders = (
        player_game_analysis.checker_blunders
        + player_game_analysis.cube_blunders
    )

    # Do not invent an Error threshold yet.
    player_game_analysis.checker_errors = None
    player_game_analysis.cube_errors = None
    player_game_analysis.errors = None

    player_game_analysis.save(
        update_fields=[
            "pr",
            "checker_pr",
            "cube_pr",
            "equity_lost",
            "checker_blunders",
            "cube_blunders",
            "blunders",
            "checker_errors",
            "cube_errors",
            "errors",
            "updated_at",
        ]
    )

    return {
        "pr": player_game_analysis.pr,
        "checker_pr": player_game_analysis.checker_pr,
        "cube_pr": player_game_analysis.cube_pr,
        "equity_lost": player_game_analysis.equity_lost,

        "decisions_analyzed": len(scoreable_all),
        "checker_decisions": len(scoreable_checker),
        "cube_decisions": len(scoreable_cube),

        "checker_blunders": (
            player_game_analysis.checker_blunders
        ),
        "cube_blunders": (
            player_game_analysis.cube_blunders
        ),
        "blunders": player_game_analysis.blunders,
    }


@transaction.atomic
def update_player_match_summary(player_match_analysis):
    player_games = list(
        player_match_analysis.games.prefetch_related(
            "decisions"
        ).all()
    )
    match_luck = sum(
        (
            player_game.luck
            or Decimal("0")
            for player_game in player_games
        ),
        Decimal("0"),
    )

    decisions = []

    for player_game in player_games:
        decisions.extend(
            list(player_game.decisions.all())
        )

    checker = [
        decision
        for decision in decisions
        if decision.decision_type in CHECKER_TYPES
    ]

    cube = [
        decision
        for decision in decisions
        if decision.decision_type in CUBE_TYPES
    ]

    scoreable_all = _scoreable(decisions)
    scoreable_checker = _scoreable(checker)
    scoreable_cube = _scoreable(cube)

    player_match_analysis.pr = calculate_pr(
        decisions
    )
    player_match_analysis.luck = match_luck

    player_match_analysis.checker_pr = calculate_pr(
        checker
    )

    player_match_analysis.cube_pr = calculate_pr(
        cube
    )

    player_match_analysis.equity_lost = (
        _sum_equity_loss(decisions)
    )

    player_match_analysis.checker_equity_lost = (
        _sum_equity_loss(checker)
    )

    player_match_analysis.cube_equity_lost = (
        _sum_equity_loss(cube)
    )

    player_match_analysis.checker_blunders = sum(
        1
        for decision in scoreable_checker
        if is_blunder(decision)
    )

    player_match_analysis.cube_blunders = sum(
        1
        for decision in scoreable_cube
        if is_blunder(decision)
    )

    player_match_analysis.blunders = (
        player_match_analysis.checker_blunders
        + player_match_analysis.cube_blunders
    )

    player_match_analysis.decisions_analyzed = (
        len(scoreable_all)
    )

    # No official Error threshold yet.
    player_match_analysis.checker_errors = None
    player_match_analysis.cube_errors = None
    player_match_analysis.errors = None

    player_match_analysis.save(
        update_fields=[
            "pr",
            "checker_pr",
            "cube_pr",
            "equity_lost",
            "checker_equity_lost",
            "cube_equity_lost",
            "checker_blunders",
            "cube_blunders",
            "blunders",
            "decisions_analyzed",
            "luck",
            "checker_errors",
            "cube_errors",
            "errors",
            "updated_at",
        ]
    )

    return {
        "pr": player_match_analysis.pr,
        "checker_pr": player_match_analysis.checker_pr,
        "cube_pr": player_match_analysis.cube_pr,

        "equity_lost": (
            player_match_analysis.equity_lost
        ),
        "checker_equity_lost": (
            player_match_analysis.checker_equity_lost
        ),
        "cube_equity_lost": (
            player_match_analysis.cube_equity_lost
        ),

        "decisions_analyzed": (
            player_match_analysis.decisions_analyzed
        ),
        "luck": player_match_analysis.luck,
        "checker_decisions": len(
            scoreable_checker
        ),
        "cube_decisions": len(
            scoreable_cube
        ),

        "checker_blunders": (
            player_match_analysis.checker_blunders
        ),
        "cube_blunders": (
            player_match_analysis.cube_blunders
        ),
        "blunders": (
            player_match_analysis.blunders
        ),
    }
