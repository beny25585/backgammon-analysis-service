from django.db import transaction

from analysis.models import (
    GameAnalysis,
    MatchAnalysis,
    PlayerGameAnalysis,
    PlayerMatchAnalysis,
)


class MatchPayloadConflict(Exception):
    pass


@transaction.atomic
def ingest_match(*, validated_data, raw_payload):
    source_match_id = validated_data["match_id"]
    source = validated_data["source"]
    players = validated_data["players"]

    analysis, created = MatchAnalysis.objects.get_or_create(
        source_match_id=source_match_id,
        defaults={
            "source_room_id": validated_data.get("room_id"),
            "source_type": source["type"],
            "tournament_id": source.get("tournament_id"),
            "fixture_id": source.get("fixture_id"),
            "schema_version": validated_data["schema_version"],
            "status": MatchAnalysis.Status.PENDING,
            "input_payload": raw_payload,
        },
    )

    if not created:
        if analysis.input_payload == raw_payload:
            return analysis, False
        raise MatchPayloadConflict(
            f"Conflicting payload for match {source_match_id}"
        )

    match_players = {}

    for color in ("white", "black"):
        match_players[color] = PlayerMatchAnalysis.objects.create(
            match_analysis=analysis,
            source_player_id=players[color]["player_id"],
            color=color,
        )

    raw_games = {
        str(game.get("game_id")): game
        for game in raw_payload.get("games", [])
        if isinstance(game, dict)
    }

    for game_data in validated_data["games"]:
        source_game_id = str(game_data["game_id"])
        raw_game = raw_games.get(source_game_id, {})
        score_before = game_data["score_before"]
        score_after = game_data["score_after"]

        game_analysis = GameAnalysis.objects.create(
            match_analysis=analysis,
            source_game_id=source_game_id,
            game_number=game_data["game_number"],

            winner=game_data["winner"],
            win_type=game_data["win_type"],
            points_awarded=game_data["points_awarded"],

            white_score_before=score_before["white"],
            black_score_before=score_before["black"],

            white_score_after=score_after["white"],
            black_score_after=score_after["black"],

            is_crawford=game_data["is_crawford"],

            input_events=raw_game.get("events", []),
        )

        for color in ("white", "black"):
            PlayerGameAnalysis.objects.create(
                game_analysis=game_analysis,
                match_player_analysis=match_players[color],
            )

    return analysis, True
