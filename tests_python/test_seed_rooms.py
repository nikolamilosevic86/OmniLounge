import re

from server.game.rooms_registry import RoomsRegistry
from server.game.room_styles import ROOM_STYLE_IDS
from server.game.seed_rooms import (
    EDUCATIONAL_ROOM_ID,
    ESCAPE_ROOM_ID,
    ESCAPE_TIME_LIMIT_MS,
    SEED_HOST_ID,
    seed_showcase_rooms,
)

YOUTUBE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


def make_registry() -> RoomsRegistry:
    registry = RoomsRegistry()
    seed_showcase_rooms(registry)
    return registry


class TestSeeding:
    def test_creates_both_rooms(self):
        registry = RoomsRegistry()
        created = seed_showcase_rooms(registry)
        assert created == [EDUCATIONAL_ROOM_ID, ESCAPE_ROOM_ID]

    def test_is_idempotent(self):
        registry = make_registry()
        assert seed_showcase_rooms(registry) == []
        assert len(registry.rooms) == 3

    def test_keeps_the_lobby(self):
        registry = make_registry()
        assert "lobby" in registry.rooms

    def test_rooms_use_their_stable_ids_everywhere(self):
        registry = make_registry()
        for room_id in (EDUCATIONAL_ROOM_ID, ESCAPE_ROOM_ID):
            assert registry.rooms[room_id].id == room_id
            assert registry.room_meta[room_id]["id"] == room_id
            assert registry.get_builder(room_id) is not None
            assert registry.get_moderation(room_id) is not None

    def test_rooms_are_listed_publicly(self):
        registry = make_registry()
        listed = {room["id"] for room in registry.list_rooms()}
        assert EDUCATIONAL_ROOM_ID in listed
        assert ESCAPE_ROOM_ID in listed

    def test_rooms_are_hosted_by_the_system_account(self):
        registry = make_registry()
        for room_id in (EDUCATIONAL_ROOM_ID, ESCAPE_ROOM_ID):
            assert registry.get_room_host_id(room_id) == SEED_HOST_ID

    def test_styles_are_real_style_ids(self):
        registry = make_registry()
        for room_id in (EDUCATIONAL_ROOM_ID, ESCAPE_ROOM_ID):
            assert registry.get_room_style(room_id) in ROOM_STYLE_IDS

    def test_each_room_uses_its_themed_style(self):
        registry = make_registry()
        assert registry.get_room_style(EDUCATIONAL_ROOM_ID) == "renaissance-studio"
        assert registry.get_room_style(ESCAPE_ROOM_ID) == "candlelit-vault"


class TestLeonardoWorkshop:
    def test_has_three_labelled_tiles(self):
        registry = make_registry()
        tiles = registry.get_room_tiles(EDUCATIONAL_ROOM_ID)
        assert len(tiles) == 3
        builder = registry.get_builder(EDUCATIONAL_ROOM_ID)
        labels = {tile["label"] for tile in builder.list_tiles()}
        assert "The Bottega" in labels
        assert "Library & Codices" in labels
        assert "Hall of Inventions" in labels

    def test_showcases_every_interactive_object_type(self):
        builder = make_registry().get_builder(EDUCATIONAL_ROOM_ID)
        types = {obj["objectType"] for obj in builder.list_objects()}
        for expected in ("bookshelf", "tv", "music_player", "ai_character", "table", "chair", "sofa"):
            assert expected in types

    def test_bookshelf_is_stocked_with_readable_books(self):
        builder = make_registry().get_builder(EDUCATIONAL_ROOM_ID)
        books = builder.list_books("lw-bookshelf")
        assert len(books) == 7
        assert len({book["bookId"] for book in books}) == len(books)
        for book in books:
            assert book["title"].strip()
            assert len(book["contentBody"]) > 200

    def test_media_ids_are_wellformed(self):
        builder = make_registry().get_builder(EDUCATIONAL_ROOM_ID)
        videos = builder.list_videos("lw-screen")
        tracks = builder.list_tracks("lw-consort")
        assert len(videos) == 4
        assert len(tracks) == 4
        for item in videos + tracks:
            assert YOUTUBE_ID_PATTERN.match(item["youtubeVideoId"])

    def test_leonardo_character_is_fully_configured(self):
        builder = make_registry().get_builder(EDUCATIONAL_ROOM_ID)
        character = builder.get_character_config("lw-leonardo")
        assert character["name"] == "Leonardo da Vinci"
        assert character["role"] == "historical_persona"
        assert character["startNodeId"] == "intro"
        assert character["knowledgeBase"]["title"]
        assert len(character["knowledgeBase"]["documents"]) == 6

    def test_story_graph_starts_at_the_start_node_and_can_end(self):
        builder = make_registry().get_builder(EDUCATIONAL_ROOM_ID)
        nodes = builder.list_story_nodes("lw-leonardo")
        node_ids = {node["nodeId"] for node in nodes}
        assert "intro" in node_ids
        assert any(node["completionFlag"] for node in nodes)

    def test_every_story_choice_points_at_a_real_node(self):
        builder = make_registry().get_builder(EDUCATIONAL_ROOM_ID)
        nodes = builder.list_story_nodes("lw-leonardo")
        node_ids = {node["nodeId"] for node in nodes}
        for node in nodes:
            for choice in node["choices"]:
                assert choice["nextNodeId"] in node_ids

    def test_has_a_guided_tour(self):
        builder = make_registry().get_builder(EDUCATIONAL_ROOM_ID)
        assert len(builder.list_character_waypoints("lw-leonardo")) == 4


class TestAlchemistVault:
    def test_escape_session_is_enabled_and_timed(self):
        builder = make_registry().get_builder(ESCAPE_ROOM_ID)
        status = builder.get_escape_status("player-1", 0.0)
        assert status["remainingMs"] == ESCAPE_TIME_LIMIT_MS
        assert builder.get_escape_briefing()
        assert builder.is_escape_team_mode() is True

    def test_has_four_puzzles_covering_every_match_mode(self):
        builder = make_registry().get_builder(ESCAPE_ROOM_ID)
        puzzles = builder.list_puzzles()
        assert len(puzzles) == 4
        assert {p["matchMode"] for p in puzzles} == {"exact", "numeric", "contains"}

    def test_every_puzzle_has_hints_and_a_prop_shape(self):
        builder = make_registry().get_builder(ESCAPE_ROOM_ID)
        for puzzle in builder.list_puzzles():
            assert puzzle["prompt"].strip()
            assert len(puzzle["hints"]) >= 1
            assert puzzle["propType"] in (
                "cipher_box", "digital_lock", "combination_dial", "riddle_tablet", "clue_board",
            )

    def test_every_puzzle_prop_object_is_bound_to_its_puzzle(self):
        builder = make_registry().get_builder(ESCAPE_ROOM_ID)
        puzzle_ids = {p["puzzleId"] for p in builder.list_puzzles()}
        bound = {
            obj["config"]["puzzleId"]
            for obj in builder.list_objects()
            if obj["config"].get("puzzleId")
        }
        assert bound == puzzle_ids

    def test_door_requires_all_four_puzzles_and_the_key(self):
        builder = make_registry().get_builder(ESCAPE_ROOM_ID)
        door = next(o for o in builder.list_objects() if o["objectId"] == "av-door")
        puzzle_ids = {p["puzzleId"] for p in builder.list_puzzles()}
        assert set(door["config"]["requiredPuzzleIds"]) == puzzle_ids
        assert door["config"]["requiredItemId"] == "av-item-key"

    def test_the_required_key_exists_as_a_hidden_item(self):
        builder = make_registry().get_builder(ESCAPE_ROOM_ID)
        key = next(o for o in builder.list_objects() if o["objectId"] == "av-item-key")
        assert key["objectType"] == "hidden_item"
        assert key["config"]["itemKind"] == "key"

    def test_the_documented_answers_actually_solve_the_puzzles(self):
        builder = make_registry().get_builder(ESCAPE_ROOM_ID)
        for puzzle_id, answer in (
            ("av-puz-year", "1452"),
            ("av-puz-smoke", "Sfumato"),
            ("av-puz-friction", "1493"),
            ("av-puz-place", "the town of Amboise"),
        ):
            result = builder.attempt_solve_puzzle(puzzle_id, "player-1", answer, 0.0)
            assert result["correct"] is True, puzzle_id

    def test_a_wrong_answer_is_rejected(self):
        builder = make_registry().get_builder(ESCAPE_ROOM_ID)
        result = builder.attempt_solve_puzzle("av-puz-year", "player-1", "1519", 0.0)
        assert result["correct"] is False

    def test_solving_the_cipher_box_reveals_the_key(self):
        builder = make_registry().get_builder(ESCAPE_ROOM_ID)
        visible = lambda: {
            obj["objectId"]
            for obj in builder.list_objects(requester_id="player-1", is_room_host=False)
        }
        assert "av-item-key" not in visible()
        builder.attempt_solve_puzzle("av-puz-smoke", "player-1", "sfumato", 0.0)
        assert "av-item-key" in visible()

    def test_apprentice_can_hint_without_giving_the_room_away(self):
        builder = make_registry().get_builder(ESCAPE_ROOM_ID)
        character = builder.get_character_config("av-apprentice")
        assert character["role"] == "guide"
        assert len(character["knowledgeBase"]["documents"]) == 1
