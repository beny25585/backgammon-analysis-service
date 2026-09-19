from rest_framework import serializers


class PlayerInputSerializer(serializers.Serializer):
    player_id = serializers.IntegerField()


class PlayersInputSerializer(serializers.Serializer):
    white = PlayerInputSerializer()
    black = PlayerInputSerializer()


class SourceInputSerializer(serializers.Serializer):
    SOURCE_TYPES = (
        ("tournament", "Tournament"),
        ("quick", "Quick"),
        ("private", "Private"),
    )

    type = serializers.ChoiceField(choices=SOURCE_TYPES)
    tournament_id = serializers.IntegerField(required=False, allow_null=True)
    fixture_id = serializers.IntegerField(required=False, allow_null=True)


class RulesInputSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=("match", "money"))
    target_points = serializers.IntegerField(min_value=1)
    time_control = serializers.CharField()
    doubling_enabled = serializers.BooleanField()
    max_cube_value = serializers.IntegerField(min_value=0)
    jacoby = serializers.BooleanField()
    beaver = serializers.BooleanField()

    def validate_max_cube_value(self, value):
        # 0 means unlimited. Otherwise only powers of two >= 2.
        if value == 0:
            return value
        if value >= 2 and (value & (value - 1)) == 0:
            return value
        raise serializers.ValidationError(
            "max_cube_value must be 0 or a power of two >= 2."
        )


class ResultInputSerializer(serializers.Serializer):
    winner = serializers.ChoiceField(choices=("white", "black"))
    white_score = serializers.IntegerField(min_value=0)
    black_score = serializers.IntegerField(min_value=0)


class GameEventInputSerializer(serializers.Serializer):
    sequence = serializers.IntegerField(min_value=0)
    event_type = serializers.CharField()
    player_color = serializers.ChoiceField(
        choices=("white", "black"),
        required=False,
        allow_null=True,
    )
    payload = serializers.JSONField()
    created_at = serializers.DateTimeField(required=False)


class ScoreInputSerializer(serializers.Serializer):
    white = serializers.IntegerField(min_value=0)
    black = serializers.IntegerField(min_value=0)


class GameInputSerializer(serializers.Serializer):
    game_id = serializers.CharField()
    game_number = serializers.IntegerField(min_value=1)
    winner = serializers.ChoiceField(choices=("white", "black"))
    win_type = serializers.CharField()
    points_awarded = serializers.IntegerField(min_value=0)
    score_before = ScoreInputSerializer()
    score_after = ScoreInputSerializer()
    is_crawford = serializers.BooleanField()
    events = GameEventInputSerializer(many=True, allow_empty=True)


class MatchAnalysisInputSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField(min_value=1, max_value=1)

    match_id = serializers.UUIDField()
    room_id = serializers.UUIDField(required=False, allow_null=True)

    source = SourceInputSerializer()
    players = PlayersInputSerializer()
    rules = RulesInputSerializer()
    result = ResultInputSerializer()

    games = GameInputSerializer(
        many=True,
        allow_empty=False,
    )

    def validate(self, attrs):
        players = attrs.get("players", {})
        white_id = players.get("white", {}).get("player_id")
        black_id = players.get("black", {}).get("player_id")
        if white_id is not None and white_id == black_id:
            raise serializers.ValidationError(
                {"players": "White and black must be different players."}
            )

        games = attrs.get("games", [])
        game_ids = [game.get("game_id") for game in games]
        if len(game_ids) != len(set(game_ids)):
            raise serializers.ValidationError(
                {"games": "Duplicate game_id in match payload."}
            )

        game_numbers = [game.get("game_number") for game in games]
        if len(game_numbers) != len(set(game_numbers)):
            raise serializers.ValidationError(
                {"games": "Duplicate game_number in match payload."}
            )

        return attrs
