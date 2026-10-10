"""Application quality labels from saved metrics; not an engine grading policy."""
from decimal import Decimal, DecimalException

from analysis.models import DecisionAnalysis
from analysis.services.scoring import BLUNDER_THRESHOLD, is_scoreable_decision


INACCURACY_THRESHOLD = Decimal("0.02")
ERROR_THRESHOLD = Decimal("0.04")


def classify_decision(decision):
    """Classify a scoreable decision without inventing missing equity loss."""
    labels = DecisionAnalysis.Classification
    if decision.equity_loss is None:
        return labels.UNCLASSIFIED
    try:
        loss = Decimal(str(decision.equity_loss))
        if not loss.is_finite() or not is_scoreable_decision(decision):
            return labels.UNCLASSIFIED
    except (DecimalException, KeyError, TypeError, ValueError, AttributeError):
        # Incomplete legacy metrics cannot establish scoreability.
        return labels.UNCLASSIFIED

    if loss > BLUNDER_THRESHOLD:
        return labels.BLUNDER
    if loss >= ERROR_THRESHOLD:
        return labels.ERROR
    if loss >= INACCURACY_THRESHOLD:
        return labels.INACCURACY
    return labels.CORRECT


def classification_counts(decisions):
    """Count disjoint error/blunder categories, ignoring stale stored labels."""
    counts = {"errors": 0, "blunders": 0}
    for decision in decisions:
        label = classify_decision(decision)
        if label == DecisionAnalysis.Classification.ERROR:
            counts["errors"] += 1
        elif label == DecisionAnalysis.Classification.BLUNDER:
            counts["blunders"] += 1
    return counts