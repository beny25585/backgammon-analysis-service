import copy


class DecisionReconstructionError(ValueError):
    pass


class GameTimelineReconstructor:
    def __init__(self, *, game: dict, rules: dict):
        if not isinstance(game, dict):
            raise DecisionReconstructionError(
                "game must be a dictionary."
            )

        if not isinstance(rules, dict):
            raise DecisionReconstructionError(
                "rules must be a dictionary."
            )

        # Work only on private copies.
        # Reconstruction must never mutate the immutable input payload.
        self.game = copy.deepcopy(game)
        self.rules = copy.deepcopy(rules)

        self.events = self._sorted_events()

        # Reconstruction state.
        # These will be populated gradually as we implement the event handlers.
        self.rolls = []
        self.decisions = []

        self.turn_number = 0

        self.pending_checker_turn = None
        self.pending_double = None

        self.previous_state = None

    def _sorted_events(self) -> list[dict]:
        events = self.game.get("events")

        if not isinstance(events, list):
            raise DecisionReconstructionError(
                'game["events"] must be a list.'
            )

        seen_sequences = set()

        for event in events:
            if not isinstance(event, dict):
                raise DecisionReconstructionError(
                    "Every game event must be a dictionary."
                )

            sequence = event.get("sequence")

            if (
                not isinstance(sequence, int)
                or isinstance(sequence, bool)
                or sequence < 0
            ):
                raise DecisionReconstructionError(
                    f"Invalid event sequence: {sequence!r}."
                )

            if sequence in seen_sequences:
                raise DecisionReconstructionError(
                    f"Duplicate event sequence: {sequence}."
                )

            seen_sequences.add(sequence)

        sorted_events = sorted(
            events,
            key=lambda event: event["sequence"],
        )

        return copy.deepcopy(sorted_events)

    def _analysis_position(
        self,
        state: dict,
        *,
        player_color: str,
    ) -> dict:
        if not isinstance(state, dict):
            raise DecisionReconstructionError(
                "State must be a dictionary."
            )

        if player_color not in ("white", "black"):
            raise DecisionReconstructionError(
                f"Invalid player color: {player_color!r}."
            )

        points = state.get("points")

        if (
            not isinstance(points, list)
            or len(points) != 24
            or any(
                not isinstance(value, int)
                or isinstance(value, bool)
                for value in points
            )
        ):
            raise DecisionReconstructionError(
                'state["points"] must contain exactly 24 integers.'
            )

        bar = state.get("bar")
        home = state.get("home")

        for name, value in (("bar", bar), ("home", home)):
            if not isinstance(value, dict):
                raise DecisionReconstructionError(
                    f'state["{name}"] must be a dictionary.'
                )

            for color in ("white", "black"):
                count = value.get(color)

                if (
                    not isinstance(count, int)
                    or isinstance(count, bool)
                    or count < 0
                ):
                    raise DecisionReconstructionError(
                        f'state["{name}"]["{color}"] must be '
                        "a non-negative integer."
                    )

        cube = state.get("cube", 1)

        if (
            not isinstance(cube, int)
            or isinstance(cube, bool)
            or cube < 1
        ):
            raise DecisionReconstructionError(
                'state["cube"] must be a positive integer.'
            )

        cube_owner = state.get("cubeOwner", "center")

        if cube_owner not in ("center", "white", "black"):
            raise DecisionReconstructionError(
                f"Invalid cube owner: {cube_owner!r}."
            )

        try:
            game_format = (
                state.get("gameFormat")
                or self.rules["format"]
            )

            if (
                "maxCube" in state
                and state["maxCube"] is not None
            ):
                max_cube = state["maxCube"]
            else:
                max_cube = self.rules["max_cube_value"]

            if "jacoby" in state:
                jacoby = state["jacoby"]
            else:
                jacoby = self.rules["jacoby"]

            if "crawfordGame" in state:
                crawford = state["crawfordGame"]
            else:
                crawford = self.game["is_crawford"]

            doubling_enabled = state.get(
                "doublingEnabled",
                self.rules["doubling_enabled"],
            )

        except KeyError as exc:
            raise DecisionReconstructionError(
                f"Missing analysis context field: {exc.args[0]}."
            ) from exc

        if (
            not isinstance(max_cube, int)
            or isinstance(max_cube, bool)
            or max_cube < 0
        ):
            raise DecisionReconstructionError(
                "maxCube must be a non-negative integer."
            )

        if not isinstance(jacoby, bool):
            raise DecisionReconstructionError(
                "jacoby must be boolean."
            )

        if not isinstance(crawford, bool):
            raise DecisionReconstructionError(
                "crawfordGame must be boolean."
            )

        if not isinstance(doubling_enabled, bool):
            raise DecisionReconstructionError(
                "doublingEnabled must be boolean."
            )

        return {
            "points": copy.deepcopy(points),
            "bar": copy.deepcopy(bar),
            "home": copy.deepcopy(home),

            # Explicitly use the player whose decision is being analyzed.
            # Do not trust state["turn"] because GameEvents are post-action
            # snapshots and the engine may already have changed the turn.
            "turn": player_color,

            "cube": cube,
            "cubeOwner": cube_owner,
            "doublingEnabled": doubling_enabled,

            "gameFormat": game_format,
            "maxCube": max_cube,
            "jacoby": jacoby,
            "crawfordGame": crawford,
        }

    @staticmethod
    def _player_occupancy(
        points: list[int],
        *,
        player_color: str,
    ) -> list[int]:
        if player_color == "white":
            return [
                max(value, 0)
                for value in points
            ]

        if player_color == "black":
            return [
                max(-value, 0)
                for value in points
            ]

        raise DecisionReconstructionError(
            f"Invalid player color: {player_color!r}."
        )

    def _infer_single_move(
        self,
        before_state: dict,
        after_state: dict,
        *,
        player_color: str,
    ) -> dict:
        if player_color not in ("white", "black"):
            raise DecisionReconstructionError(
                f"Invalid player color: {player_color!r}."
            )

        try:
            before_points = before_state["points"]
            after_points = after_state["points"]

            before_bar = before_state["bar"][player_color]
            after_bar = after_state["bar"][player_color]

            before_home = before_state["home"][player_color]
            after_home = after_state["home"][player_color]

        except (KeyError, TypeError) as exc:
            raise DecisionReconstructionError(
                "Cannot infer move from malformed state."
            ) from exc

        if (
            not isinstance(before_points, list)
            or not isinstance(after_points, list)
            or len(before_points) != 24
            or len(after_points) != 24
        ):
            raise DecisionReconstructionError(
                "Cannot infer move: points must contain 24 entries."
            )

        before_occupancy = self._player_occupancy(
            before_points,
            player_color=player_color,
        )

        after_occupancy = self._player_occupancy(
            after_points,
            player_color=player_color,
        )

        point_deltas = [
            after - before
            for before, after in zip(
                before_occupancy,
                after_occupancy,
            )
        ]

        if any(
            delta not in (-1, 0, 1)
            for delta in point_deltas
        ):
            raise DecisionReconstructionError(
                "Cannot infer a single move from the board difference."
            )

        decreased_points = [
            index
            for index, delta in enumerate(point_deltas)
            if delta == -1
        ]

        increased_points = [
            index
            for index, delta in enumerate(point_deltas)
            if delta == 1
        ]

        bar_delta = after_bar - before_bar
        home_delta = after_home - before_home

        if bar_delta not in (-1, 0):
            raise DecisionReconstructionError(
                "Cannot infer a single move from the bar difference."
            )

        if home_delta not in (0, 1):
            raise DecisionReconstructionError(
                "Cannot infer a single move from the home difference."
            )

        # Determine FROM.
        if bar_delta == -1:
            if decreased_points:
                raise DecisionReconstructionError(
                    "Ambiguous move origin."
                )

            move_from = "bar"

        else:
            if len(decreased_points) != 1:
                raise DecisionReconstructionError(
                    "Cannot determine move origin."
                )

            move_from = decreased_points[0]

        # Determine TO.
        if home_delta == 1:
            if increased_points:
                raise DecisionReconstructionError(
                    "Ambiguous move destination."
                )

            move_to = "off"

        else:
            if len(increased_points) != 1:
                raise DecisionReconstructionError(
                    "Cannot determine move destination."
                )

            move_to = increased_points[0]

        return {
            "from": move_from,
            "to": move_to,
        }
