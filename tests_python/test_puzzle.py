import pytest

from server.game.puzzle import ATTEMPT_RATE_LIMIT_MAX_REQUESTS, PuzzleEngine


class TestAddPuzzle:
    def test_add_puzzle_returns_public_dict_without_answer(self):
        engine = PuzzleEngine()
        result = engine.add_puzzle("p1", prompt="2+2?", answer="4", hints=["think addition"])
        assert result["puzzleId"] == "p1"
        assert result["prompt"] == "2+2?"
        assert "answer" not in result
        assert result["hints"] == ["think addition"]

    def test_add_puzzle_defaults(self):
        engine = PuzzleEngine()
        result = engine.add_puzzle("p1", prompt="2+2?", answer="4")
        assert result["hints"] == []
        assert result["revealItemId"] is None
        assert result["unlockDoorId"] is None
        assert result["matchMode"] == "exact"
        assert result["maxAttempts"] is None

    def test_rejects_duplicate_puzzle_id(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="b")
        with pytest.raises(ValueError, match="already exists"):
            engine.add_puzzle("p1", prompt="c", answer="d")

    @pytest.mark.parametrize("prompt", ["", "   "])
    def test_rejects_blank_prompt(self, prompt):
        engine = PuzzleEngine()
        with pytest.raises(ValueError, match="prompt is required"):
            engine.add_puzzle("p1", prompt=prompt, answer="b")

    @pytest.mark.parametrize("answer", ["", "   "])
    def test_rejects_blank_answer(self, answer):
        engine = PuzzleEngine()
        with pytest.raises(ValueError, match="answer is required"):
            engine.add_puzzle("p1", prompt="a", answer=answer)

    def test_rejects_invalid_match_mode(self):
        engine = PuzzleEngine()
        with pytest.raises(ValueError, match="match_mode"):
            engine.add_puzzle("p1", prompt="a", answer="b", match_mode="fuzzy")

    @pytest.mark.parametrize("max_attempts", [0, -1])
    def test_rejects_non_positive_max_attempts(self, max_attempts):
        engine = PuzzleEngine()
        with pytest.raises(ValueError, match="max_attempts"):
            engine.add_puzzle("p1", prompt="a", answer="b", max_attempts=max_attempts)


class TestGetPuzzlePublicAndRemove:
    def test_get_puzzle_public_unknown_raises_key_error(self):
        engine = PuzzleEngine()
        with pytest.raises(KeyError):
            engine.get_puzzle_public("nope")

    def test_remove_puzzle_returns_true_then_false(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="b")
        assert engine.remove_puzzle("p1") is True
        assert engine.remove_puzzle("p1") is False
        with pytest.raises(KeyError):
            engine.get_puzzle_public("p1")

    def test_remove_puzzle_clears_per_user_state(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="b", max_attempts=1)
        engine.attempt_solve("p1", "u1", "wrong", now_ms=0.0)
        engine.request_hint("p1", "u1", now_ms=0.0)
        engine.remove_puzzle("p1")
        engine.add_puzzle("p1", prompt="a", answer="b", max_attempts=1)
        # A fresh puzzle re-using the same id must not inherit stale lockout
        # or hint-usage state from the deleted puzzle.
        result = engine.attempt_solve("p1", "u1", "b", now_ms=0.0)
        assert result == {"correct": True, "attemptsRemaining": 1, "alreadySolved": False, "locked": False}

    def test_list_puzzles_returns_public_dicts(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="b")
        engine.add_puzzle("p2", prompt="c", answer="d")
        ids = {p["puzzleId"] for p in engine.list_puzzles()}
        assert ids == {"p1", "p2"}
        assert all("answer" not in p for p in engine.list_puzzles())


class TestIsSolved:
    def test_defaults_to_false(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="b")
        assert engine.is_solved("p1", "u1") is False


class TestAttemptSolveMatchModes:
    def test_exact_match_is_case_insensitive_and_trims_whitespace(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="Name a color", answer="Blue")
        result = engine.attempt_solve("p1", "u1", "  blue  ", now_ms=0.0)
        assert result["correct"] is True
        assert engine.is_solved("p1", "u1") is True

    def test_exact_match_rejects_wrong_guess(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="Name a color", answer="Blue")
        result = engine.attempt_solve("p1", "u1", "red", now_ms=0.0)
        assert result["correct"] is False
        assert engine.is_solved("p1", "u1") is False

    def test_numeric_match_mode_compares_numeric_value(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="year?", answer="1815", match_mode="numeric")
        assert engine.attempt_solve("p1", "u1", "1815.0", now_ms=0.0)["correct"] is True

    def test_numeric_match_mode_rejects_non_numeric_guess(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="year?", answer="1815", match_mode="numeric")
        assert engine.attempt_solve("p1", "u1", "not a number", now_ms=0.0)["correct"] is False

    def test_contains_match_mode_accepts_keyword_inside_longer_guess(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="what did the note say?", answer="brass key", match_mode="contains")
        result = engine.attempt_solve("p1", "u1", "the note mentions a BRASS KEY hidden somewhere", now_ms=0.0)
        assert result["correct"] is True

    def test_contains_match_mode_rejects_guess_missing_keyword(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="what did the note say?", answer="brass key", match_mode="contains")
        result = engine.attempt_solve("p1", "u1", "a silver coin", now_ms=0.0)
        assert result["correct"] is False


class TestAttemptSolveUnknownPuzzle:
    def test_raises_key_error(self):
        engine = PuzzleEngine()
        with pytest.raises(KeyError):
            engine.attempt_solve("nope", "u1", "guess", now_ms=0.0)


class TestAttemptSolvePerUserIsolation:
    def test_two_users_solve_independently(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="42")
        engine.attempt_solve("p1", "u1", "42", now_ms=0.0)
        assert engine.is_solved("p1", "u1") is True
        assert engine.is_solved("p1", "u2") is False

    def test_one_users_lockout_does_not_affect_another(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="42", max_attempts=1)
        engine.attempt_solve("p1", "u1", "wrong", now_ms=0.0)
        locked_result = engine.attempt_solve("p1", "u1", "42", now_ms=1.0)
        assert locked_result["locked"] is True
        # u2 has never guessed, so they should be unaffected by u1's lockout.
        other_result = engine.attempt_solve("p1", "u2", "42", now_ms=1.0)
        assert other_result == {"correct": True, "attemptsRemaining": 1, "alreadySolved": False, "locked": False}


class TestAttemptSolveAlreadySolved:
    def test_already_solved_short_circuits_without_checking_guess(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="42")
        engine.attempt_solve("p1", "u1", "42", now_ms=0.0)
        result = engine.attempt_solve("p1", "u1", "totally wrong", now_ms=1.0)
        assert result["correct"] is True
        assert result["alreadySolved"] is True


class TestAttemptLockoutAndReset:
    def test_locks_after_max_attempts_wrong_guesses(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="42", max_attempts=2)
        first = engine.attempt_solve("p1", "u1", "wrong", now_ms=0.0)
        assert first == {"correct": False, "attemptsRemaining": 1, "alreadySolved": False, "locked": False}
        second = engine.attempt_solve("p1", "u1", "wrong again", now_ms=1.0)
        assert second == {"correct": False, "attemptsRemaining": 0, "alreadySolved": False, "locked": True}

    def test_locked_out_user_cannot_solve_even_with_correct_guess(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="42", max_attempts=1)
        engine.attempt_solve("p1", "u1", "wrong", now_ms=0.0)
        result = engine.attempt_solve("p1", "u1", "42", now_ms=1.0)
        assert result["correct"] is False
        assert result["locked"] is True
        assert engine.is_solved("p1", "u1") is False

    def test_reset_attempts_clears_lockout_but_not_solved_state(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="42", max_attempts=1)
        engine.attempt_solve("p1", "u1", "wrong", now_ms=0.0)
        engine.reset_attempts("p1", "u1")
        result = engine.attempt_solve("p1", "u1", "42", now_ms=1.0)
        assert result == {"correct": True, "attemptsRemaining": 1, "alreadySolved": False, "locked": False}

    def test_reset_attempts_on_solved_puzzle_leaves_it_solved(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="42", max_attempts=1)
        engine.attempt_solve("p1", "u1", "42", now_ms=0.0)
        engine.reset_attempts("p1", "u1")
        assert engine.is_solved("p1", "u1") is True

    def test_reset_attempts_unknown_puzzle_raises_key_error(self):
        engine = PuzzleEngine()
        with pytest.raises(KeyError):
            engine.reset_attempts("nope", "u1")


class TestAttemptRateLimiting:
    def test_guesses_beyond_burst_limit_are_blocked_without_consuming_an_attempt(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="42", max_attempts=100)
        for _ in range(ATTEMPT_RATE_LIMIT_MAX_REQUESTS):
            result = engine.attempt_solve("p1", "u1", "wrong", now_ms=0.0)
            assert result["locked"] is False
        blocked = engine.attempt_solve("p1", "u1", "wrong", now_ms=0.0)
        assert blocked == {
            "correct": False,
            "attemptsRemaining": 100 - ATTEMPT_RATE_LIMIT_MAX_REQUESTS,
            "alreadySolved": False,
            "locked": False,
        }

    def test_rate_limit_resets_outside_the_window(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="42")
        for _ in range(ATTEMPT_RATE_LIMIT_MAX_REQUESTS):
            engine.attempt_solve("p1", "u1", "wrong", now_ms=0.0)
        # Far outside the rate-limit window: this guess should be evaluated
        # again (and succeed), not blocked.
        result = engine.attempt_solve("p1", "u1", "42", now_ms=1_000_000.0)
        assert result["correct"] is True


class TestRequestHint:
    def test_returns_hints_in_order_and_tracks_usage(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="b", hints=["first hint", "second hint"])
        first = engine.request_hint("p1", "u1", now_ms=0.0)
        assert first == {"hint": "first hint", "hintsUsed": 1, "hintsRemaining": 1}
        second = engine.request_hint("p1", "u1", now_ms=1.0)
        assert second == {"hint": "second hint", "hintsUsed": 2, "hintsRemaining": 0}

    def test_exhausted_hints_returns_none(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="b", hints=["only hint"])
        engine.request_hint("p1", "u1", now_ms=0.0)
        result = engine.request_hint("p1", "u1", now_ms=1.0)
        assert result == {"hint": None, "hintsUsed": 1, "hintsRemaining": 0}

    def test_no_hints_configured_returns_none_immediately(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="b")
        result = engine.request_hint("p1", "u1", now_ms=0.0)
        assert result == {"hint": None, "hintsUsed": 0, "hintsRemaining": 0}

    def test_hint_usage_is_isolated_per_user(self):
        engine = PuzzleEngine()
        engine.add_puzzle("p1", prompt="a", answer="b", hints=["first hint"])
        engine.request_hint("p1", "u1", now_ms=0.0)
        result = engine.request_hint("p1", "u2", now_ms=0.0)
        assert result == {"hint": "first hint", "hintsUsed": 1, "hintsRemaining": 0}

    def test_unknown_puzzle_raises_key_error(self):
        engine = PuzzleEngine()
        with pytest.raises(KeyError):
            engine.request_hint("nope", "u1", now_ms=0.0)
