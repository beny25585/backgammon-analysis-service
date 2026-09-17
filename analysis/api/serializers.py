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
    format = serializers.CharField()
    target_points = serializers.IntegerField(min_value=1)
    time_control = serializers.CharField()
    doubling_enabled = serializers.BooleanField()


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


class GameInputSerializer(serializers.Serializer):
    game_id = serializers.CharField()
    game_number = serializers.IntegerField(min_value=1)
    winner = serializers.ChoiceField(choices=("white", "black"))
    win_type = serializers.CharField()
    points_awarded = serializers.IntegerField(min_value=0)
    events = GameEventInputSerializer(many=True)


class MatchAnalysisInputSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField(min_value=1)

    match_id = serializers.UUIDField()
    room_id = serializers.UUIDField(required=False, allow_null=True)

    source = SourceInputSerializer()
    players = PlayersInputSerializer()
    rules = RulesInputSerializer()
    result = ResultInputSerializer()

    games = GameInputSerializer(many=True)
