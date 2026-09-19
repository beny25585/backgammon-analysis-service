from decimal import Decimal

from analysis.models import DecisionAnalysis


TRIVIAL_SPREAD = Decimal("0.001")
BLUNDER_THRESHOLD = Decimal("0.08")
PR_MULTIPLIER = Decimal("500")


CHECKER_TYPES = {
    DecisionAnalysis.DecisionType.CHECKER_MOVE,
}

CUBE_DOUBLE_TYPES = {
    DecisionAnalysis.DecisionType.NO_DOUBLE,
    DecisionAnalysis.DecisionType.DOUBLE,
    DecisionAnalysis.DecisionType.REDOUBLE,
}

CUBE_RESPONSE_TYPES = {
    DecisionAnalysis.DecisionType.TAKE,
    DecisionAnalysis.DecisionType.PASS,
}

CUBE_TYPES = CUBE_DOUBLE_TYPES | CUBE_RESPONSE_TYPES


def _decimal(value):
    return Decimal(str(value))


def is_scoreable_checker(decision):
    raw = decision.raw_analysis or {}
    moves = raw.get("moves") or []

    # Forced move / no real choice.
    if len(moves) < 2:
        return False

    best_equity = _decimal(moves[0]["equity"])
    worst_equity = _decimal(moves[-1]["equity"])

    spread = best_equity - worst_equity

    return spread >= TRIVIAL_SPREAD


def _cube_equities(decision):
    raw = decision.raw_analysis or {}
    equities = raw.get("equities") or {}

    try:
        nd = _decimal(equities["no_double"])
        dt = _decimal(equities["double_take"])
        dp = _decimal(equities["double_pass"])
    except (KeyError, TypeError, ValueError):
        return None

    return nd, dt, dp


def is_scoreable_cube(decision):
    equities = _cube_equities(decision)

    if equities is None:
        return False

    nd, dt, dp = equities

    if decision.decision_type in CUBE_DOUBLE_TYPES:
        # Same trivial-cube rules used by Open Sage's PR benchmark.
        if abs(nd - dt) < TRIVIAL_SPREAD:
            return False

        if nd - dt > Decimal("0.200"):
            return False

        if nd - dp > Decimal("0.200"):
            return False

        if (
            nd < Decimal("-0.900")
            and dt < Decimal("-0.900")
        ):
            return False

        return True

    if decision.decision_type in CUBE_RESPONSE_TYPES:
        raw = decision.raw_analysis or {}

        is_beaver = bool(
            raw.get("is_beaver", False)
        )

        return (
            abs(dt - dp) >= TRIVIAL_SPREAD
            or is_beaver
        )

    return False


def is_scoreable_decision(decision):
    if decision.decision_type in CHECKER_TYPES:
        return is_scoreable_checker(decision)

    if decision.decision_type in CUBE_TYPES:
        return is_scoreable_cube(decision)

    return False


def is_blunder(decision):
    if not is_scoreable_decision(decision):
        return False

    if decision.equity_loss is None:
        return False

    return (
        decision.equity_loss
        > BLUNDER_THRESHOLD
    )


def calculate_pr(decisions):
    scoreable = [
        decision
        for decision in decisions
        if is_scoreable_decision(decision)
        and decision.equity_loss is not None
    ]

    if not scoreable:
        return Decimal("0")

    total_error = sum(
        (
            decision.equity_loss
            for decision in scoreable
        ),
        Decimal("0"),
    )

    return (
        total_error
        / Decimal(len(scoreable))
        * PR_MULTIPLIER
    )
