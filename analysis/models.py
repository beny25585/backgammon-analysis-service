from django.db import models

# Create your models here.

import uuid

from django.db import models


class MatchAnalysis(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class SourceType(models.TextChoices):
        TOURNAMENT = "tournament", "Tournament"
        QUICK = "quick", "Quick"
        PRIVATE = "private", "Private"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # IDs from Backgammon Game — no cross-service ForeignKey.
    source_match_id = models.UUIDField(unique=True)
    source_room_id = models.UUIDField(null=True, blank=True)

    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
    )
    tournament_id = models.BigIntegerField(null=True, blank=True)
    fixture_id = models.BigIntegerField(null=True, blank=True)

    schema_version = models.PositiveIntegerField(default=1)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    engine = models.CharField(max_length=50, blank=True, default="")
    engine_version = models.CharField(max_length=100, blank=True, default="")
    eval_level = models.CharField(max_length=10, default="1ply")

    # Exact immutable package received from Backgammon Game.
    input_payload = models.JSONField()

    # Full response from the analysis engine, useful for debugging/re-analysis.
    raw_response = models.JSONField(null=True, blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Analysis {self.source_match_id} ({self.status})"


class GameAnalysis(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    match_analysis = models.ForeignKey(
        MatchAnalysis,
        on_delete=models.CASCADE,
        related_name="games",
    )

    source_game_id = models.CharField(max_length=100)
    game_number = models.PositiveIntegerField()

    winner = models.CharField(
        max_length=5,
        choices=(("white", "White"), ("black", "Black")),
    )
    win_type = models.CharField(max_length=30)
    points_awarded = models.PositiveIntegerField(default=0)
    white_score_before = models.PositiveIntegerField(default=0)
    black_score_before = models.PositiveIntegerField(default=0)

    white_score_after = models.PositiveIntegerField(default=0)
    black_score_after = models.PositiveIntegerField(default=0)

    is_crawford = models.BooleanField(default=False)

    # Events belonging only to this game.
    input_events = models.JSONField(default=list)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("game_number",)
        constraints = [
            models.UniqueConstraint(
                fields=("match_analysis", "game_number"),
                name="unique_analysis_game_number",
            ),
            models.UniqueConstraint(
                fields=("match_analysis", "source_game_id"),
                name="unique_analysis_source_game",
            ),
        ]

    def __str__(self):
        return f"Game {self.game_number} of {self.match_analysis_id}"


class PlayerMatchAnalysis(models.Model):
    COLOR_CHOICES = (
        ("white", "White"),
        ("black", "Black"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    match_analysis = models.ForeignKey(
        MatchAnalysis,
        on_delete=models.CASCADE,
        related_name="players",
    )

    # Player PK from Backgammon Game.
    source_player_id = models.BigIntegerField(db_index=True)
    color = models.CharField(max_length=5, choices=COLOR_CHOICES)

    # Result-screen summary + match-level statistics.
    pr = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    game_rating = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    luck = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )

    equity_lost = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )

    checker_pr = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    checker_equity_lost = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    checker_errors = models.PositiveIntegerField(null=True, blank=True)
    checker_blunders = models.PositiveIntegerField(null=True, blank=True)

    cube_pr = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    cube_equity_lost = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    cube_errors = models.PositiveIntegerField(null=True, blank=True)
    cube_blunders = models.PositiveIntegerField(null=True, blank=True)

    errors = models.PositiveIntegerField(null=True, blank=True)
    blunders = models.PositiveIntegerField(null=True, blank=True)
    decisions_analyzed = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("match_analysis", "color"),
                name="unique_match_analysis_color",
            ),
            models.UniqueConstraint(
                fields=("match_analysis", "source_player_id"),
                name="unique_match_analysis_player",
            ),
        ]

    def __str__(self):
        return f"{self.color} analysis for {self.match_analysis_id}"


class PlayerGameAnalysis(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    game_analysis = models.ForeignKey(
        GameAnalysis,
        on_delete=models.CASCADE,
        related_name="players",
    )

    match_player_analysis = models.ForeignKey(
        PlayerMatchAnalysis,
        on_delete=models.CASCADE,
        related_name="games",
    )

    pr = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    game_rating = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    luck = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    equity_lost = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )

    checker_pr = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    checker_errors = models.PositiveIntegerField(null=True, blank=True)
    checker_blunders = models.PositiveIntegerField(null=True, blank=True)

    cube_pr = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    cube_errors = models.PositiveIntegerField(null=True, blank=True)
    cube_blunders = models.PositiveIntegerField(null=True, blank=True)

    errors = models.PositiveIntegerField(null=True, blank=True)
    blunders = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("game_analysis", "match_player_analysis"),
                name="unique_game_player_analysis",
            ),
        ]

    def __str__(self):
        return f"Player analysis for game {self.game_analysis_id}"


class DecisionAnalysis(models.Model):
    class DecisionType(models.TextChoices):
        CHECKER_MOVE = "checker_move", "Checker move"
        DOUBLE = "double", "Double"
        NO_DOUBLE = "no_double", "No double"
        TAKE = "take", "Take"
        PASS = "pass", "Pass"
        REDOUBLE = "redouble", "Redouble"
        TOO_GOOD = "too_good", "Too good"

    class Classification(models.TextChoices):
        UNCLASSIFIED = "unclassified", "Unclassified"
        CORRECT = "correct", "Correct"
        INACCURACY = "inaccuracy", "Inaccuracy"
        ERROR = "error", "Error"
        BLUNDER = "blunder", "Blunder"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    player_game_analysis = models.ForeignKey(
        PlayerGameAnalysis,
        on_delete=models.CASCADE,
        related_name="decisions",
    )

    sequence_number = models.PositiveIntegerField()
    turn_number = models.PositiveIntegerField(null=True, blank=True)

    # Corresponding sequence from GameEvent when available.
    source_event_sequence = models.IntegerField(null=True, blank=True)

    decision_type = models.CharField(
        max_length=30,
        choices=DecisionType.choices,
    )

    dice = models.JSONField(default=list, blank=True)

    played_action = models.JSONField(null=True, blank=True)
    best_action = models.JSONField(null=True, blank=True)
    alternatives = models.JSONField(default=list, blank=True)

    played_equity = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    best_equity = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )
    equity_loss = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True
    )

    classification = models.CharField(
        max_length=20,
        choices=Classification.choices,
        default=Classification.UNCLASSIFIED,
    )

    # Board immediately before the decision.
    position_snapshot = models.JSONField(default=dict, blank=True)

    # Engine-specific detail. UI/API should not depend directly on its shape.
    raw_analysis = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("sequence_number",)
        constraints = [
            models.UniqueConstraint(
                fields=("player_game_analysis", "sequence_number"),
                name="unique_player_decision_sequence",
            ),
        ]

    def __str__(self):
        return (
            f"{self.decision_type} #{self.sequence_number} "
            f"for {self.player_game_analysis_id}"
        )


class RollLuckAnalysis(models.Model):
    player_game_analysis = models.ForeignKey(
        PlayerGameAnalysis,
        on_delete=models.CASCADE,
        related_name="luck_rolls",
    )

    source_event_sequence = models.PositiveIntegerField()

    dice = models.JSONField(
        default=list,
    )

    is_opening_roll = models.BooleanField(
        default=False,
    )

    luck = models.DecimalField(
        max_digits=12,
        decimal_places=8,
    )

    actual_equity = models.DecimalField(
        max_digits=12,
        decimal_places=8,
    )

    average_equity = models.DecimalField(
        max_digits=12,
        decimal_places=8,
    )

    ply = models.PositiveSmallIntegerField()

    level_label = models.CharField(
        max_length=32,
        blank=True,
        default="",
    )

    position_snapshot = models.JSONField(
        default=dict,
    )

    raw_analysis = models.JSONField(
        default=dict,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "source_event_sequence",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "player_game_analysis",
                    "source_event_sequence",
                ],
                name=(
                    "unique_player_game_luck_roll"
                ),
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "player_game_analysis",
                    "source_event_sequence",
                ],
                name="luck_player_seq_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.player_game_analysis_id} "
            f"roll={self.source_event_sequence} "
            f"luck={self.luck}"
        )
