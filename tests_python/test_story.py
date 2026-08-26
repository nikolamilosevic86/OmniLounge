"""Tests for Phase H domain logic: AI story characters, predefined story
graph traversal, knowledge base, and the generative-mode fallback flow."""

import pytest
from pydantic import ValidationError

from server.game.story import StoryEngine


class TestAddCharacter:
    def setup_method(self):
        self.engine = StoryEngine()

    def test_add_character_returns_record_with_all_fields(self):
        char = self.engine.add_character(
            "npc-1", "char-1", name="Professor Owl", role="guide",
            start_node_id="node-1", portrait_url="https://example.com/owl.png",
        )
        assert char["characterId"] == "char-1"
        assert char["name"] == "Professor Owl"
        assert char["role"] == "guide"
        assert char["startNodeId"] == "node-1"
        assert char["portraitUrl"] == "https://example.com/owl.png"
        assert char["generativeEnabled"] is False

    def test_add_character_never_includes_api_key_field(self):
        char = self.engine.add_character("npc-1", "char-1", name="Owl", role="guide", start_node_id="node-1")
        assert "apiKey" not in char

    def test_add_character_rejects_invalid_role(self):
        with pytest.raises(ValueError):
            self.engine.add_character("npc-1", "char-1", name="Owl", role="wizard", start_node_id="node-1")

    def test_add_character_rejects_empty_name(self):
        with pytest.raises(ValueError):
            self.engine.add_character("npc-1", "char-1", name="  ", role="guide", start_node_id="node-1")

    def test_add_character_rejects_duplicate_id_on_same_object(self):
        self.engine.add_character("npc-1", "char-1", name="Owl", role="guide", start_node_id="node-1")
        with pytest.raises(ValueError):
            self.engine.add_character("npc-1", "char-1", name="Owl2", role="mentor", start_node_id="node-1")


class TestListAndRemoveCharacter:
    def setup_method(self):
        self.engine = StoryEngine()
        self.engine.add_character("npc-1", "char-1", name="Owl", role="guide", start_node_id="node-1")

    def test_list_characters_returns_all(self):
        assert [c["characterId"] for c in self.engine.list_characters("npc-1")] == ["char-1"]

    def test_list_characters_empty_for_unknown_object(self):
        assert self.engine.list_characters("unknown") == []

    def test_get_character_returns_none_for_unknown(self):
        assert self.engine.get_character("npc-1", "unknown") is None

    def test_remove_character_returns_true_and_removes(self):
        assert self.engine.remove_character("npc-1", "char-1") is True
        assert self.engine.get_character("npc-1", "char-1") is None

    def test_remove_unknown_character_returns_false(self):
        assert self.engine.remove_character("npc-1", "unknown") is False


class TestKnowledgeBase:
    def setup_method(self):
        self.engine = StoryEngine()
        self.engine.add_character("npc-1", "char-1", name="Owl", role="guide", start_node_id="node-1")

    def test_set_knowledge_base_updates_character(self):
        char = self.engine.set_knowledge_base("npc-1", "char-1", "Owls are nocturnal birds of prey.")
        assert char["knowledgeBase"] == "Owls are nocturnal birds of prey."

    def test_set_knowledge_base_raises_for_unknown_character(self):
        with pytest.raises(KeyError):
            self.engine.set_knowledge_base("npc-1", "unknown", "content")


class TestGenerativeConfig:
    def setup_method(self):
        self.engine = StoryEngine()
        self.engine.add_character("npc-1", "char-1", name="Owl", role="guide", start_node_id="node-1")

    def test_configure_generative_mode_enables_when_both_url_and_key_present(self):
        char = self.engine.configure_generative_mode(
            "npc-1", "char-1", api_base_url="https://api.example.com/v1", api_key="secret",
        )
        assert char["generativeEnabled"] is True

    def test_configure_generative_mode_stays_disabled_when_key_missing(self):
        char = self.engine.configure_generative_mode("npc-1", "char-1", api_base_url="https://api.example.com/v1")
        assert char["generativeEnabled"] is False

    def test_configure_generative_mode_stays_disabled_when_url_missing(self):
        char = self.engine.configure_generative_mode("npc-1", "char-1", api_key="secret")
        assert char["generativeEnabled"] is False

    def test_configure_generative_mode_never_exposes_api_key(self):
        char = self.engine.configure_generative_mode(
            "npc-1", "char-1", api_base_url="https://api.example.com/v1", api_key="secret",
        )
        assert "apiKey" not in char

    def test_clearing_api_key_disables_generative_mode(self):
        self.engine.configure_generative_mode("npc-1", "char-1", api_base_url="https://api.example.com/v1", api_key="secret")
        char = self.engine.configure_generative_mode("npc-1", "char-1", api_base_url="https://api.example.com/v1")
        assert char["generativeEnabled"] is False

    def test_configure_generative_mode_rejects_loopback_url_ssrf_guard(self):
        with pytest.raises(ValueError):
            self.engine.configure_generative_mode(
                "npc-1", "char-1", api_base_url="http://127.0.0.1/v1", api_key="secret",
            )

    def test_configure_generative_mode_rejects_cloud_metadata_url_ssrf_guard(self):
        with pytest.raises(ValueError):
            self.engine.configure_generative_mode(
                "npc-1", "char-1", api_base_url="http://169.254.169.254/latest/meta-data/", api_key="secret",
            )

    def test_configure_generative_mode_rejects_non_http_scheme(self):
        with pytest.raises(ValueError):
            self.engine.configure_generative_mode(
                "npc-1", "char-1", api_base_url="file:///etc/passwd", api_key="secret",
            )

    def test_configure_generative_mode_allows_clearing_url_to_none_even_though_unsafe_would_be_rejected(self):
        char = self.engine.configure_generative_mode("npc-1", "char-1", api_base_url=None, api_key="secret")
        assert char["generativeEnabled"] is False


class TestStoryNodes:
    def setup_method(self):
        self.engine = StoryEngine()
        self.engine.add_character("npc-1", "char-1", name="Owl", role="guide", start_node_id="node-1")

    def test_add_story_node_returns_record_with_all_fields(self):
        node = self.engine.add_story_node(
            "npc-1", "char-1", "node-1", character_line="Welcome, traveler.",
            choices=[{"text": "Tell me more", "nextNodeId": "node-2"}],
        )
        assert node["nodeId"] == "node-1"
        assert node["characterLine"] == "Welcome, traveler."
        assert node["choices"] == [{"text": "Tell me more", "nextNodeId": "node-2"}]
        assert node["completionFlag"] is False

    def test_add_story_node_rejects_empty_character_line(self):
        with pytest.raises(ValidationError):
            self.engine.add_story_node("npc-1", "char-1", "node-1", character_line="")

    def test_add_story_node_rejects_unknown_character(self):
        with pytest.raises(KeyError):
            self.engine.add_story_node("npc-1", "unknown-char", "node-1", character_line="Hi")

    def test_get_story_node_returns_none_for_unknown(self):
        assert self.engine.get_story_node("npc-1", "char-1", "unknown") is None

    def test_list_story_nodes_returns_all(self):
        self.engine.add_story_node("npc-1", "char-1", "node-1", character_line="Hi")
        self.engine.add_story_node("npc-1", "char-1", "node-2", character_line="Bye")
        assert {n["nodeId"] for n in self.engine.list_story_nodes("npc-1", "char-1")} == {"node-1", "node-2"}


class TestTalkProgression:
    def setup_method(self):
        self.engine = StoryEngine()
        self.engine.add_character("npc-1", "char-1", name="Owl", role="guide", start_node_id="node-1")
        self.engine.add_story_node(
            "npc-1", "char-1", "node-1", character_line="Welcome!",
            choices=[{"text": "Continue", "nextNodeId": "node-2"}],
        )
        self.engine.add_story_node(
            "npc-1", "char-1", "node-2", character_line="The end.", completion_flag=True,
        )

    def test_talk_with_no_prior_progress_starts_at_the_start_node(self):
        result = self.engine.talk("npc-1", "char-1", user_id="p1")
        assert result["node"]["nodeId"] == "node-1"
        assert result["mode"] == "predefined"

    def test_talk_with_choice_index_advances_to_next_node(self):
        self.engine.talk("npc-1", "char-1", user_id="p1")
        result = self.engine.talk("npc-1", "char-1", user_id="p1", choice_index=0)
        assert result["node"]["nodeId"] == "node-2"

    def test_talk_progress_persists_across_calls(self):
        self.engine.talk("npc-1", "char-1", user_id="p1", choice_index=0)
        result = self.engine.talk("npc-1", "char-1", user_id="p1")
        assert result["node"]["nodeId"] == "node-2"

    def test_talk_progress_is_scoped_per_user(self):
        self.engine.talk("npc-1", "char-1", user_id="p1", choice_index=0)
        result = self.engine.talk("npc-1", "char-1", user_id="p2")
        assert result["node"]["nodeId"] == "node-1"

    def test_talk_rejects_out_of_range_choice_index(self):
        self.engine.talk("npc-1", "char-1", user_id="p1")
        with pytest.raises(ValueError):
            self.engine.talk("npc-1", "char-1", user_id="p1", choice_index=5)

    def test_talk_raises_for_unknown_character(self):
        with pytest.raises(KeyError):
            self.engine.talk("npc-1", "unknown-char", user_id="p1")

    def test_restart_story_resets_progress_to_start_node(self):
        self.engine.talk("npc-1", "char-1", user_id="p1", choice_index=0)
        result = self.engine.restart_story("npc-1", "char-1", user_id="p1")
        assert result["node"]["nodeId"] == "node-1"


class TestGenerativeAnswer:
    def setup_method(self):
        self.engine = StoryEngine()
        self.engine.add_character("npc-1", "char-1", name="Owl", role="guide", start_node_id="node-1")

    def test_ask_generative_returns_predefined_fallback_when_disabled(self):
        result = self.engine.ask_generative("npc-1", "char-1", "What is 2+2?", caller=lambda *a: "4")
        assert result["mode"] == "predefined"

    def test_ask_generative_fallback_uses_knowledge_base_when_present(self):
        self.engine.set_knowledge_base("npc-1", "char-1", "Owls are nocturnal.")
        result = self.engine.ask_generative("npc-1", "char-1", "Tell me about owls", caller=lambda *a: "ignored")
        assert result["answer"] == "Owls are nocturnal."
        assert result["mode"] == "predefined"

    def test_ask_generative_calls_caller_and_returns_its_answer_when_enabled(self):
        self.engine.configure_generative_mode("npc-1", "char-1", api_base_url="https://api.example.com", api_key="secret")
        captured = {}

        def fake_caller(api_base_url, api_key, knowledge_base, user_message):
            captured["args"] = (api_base_url, api_key, knowledge_base, user_message)
            return "A generated answer."

        result = self.engine.ask_generative("npc-1", "char-1", "What is 2+2?", caller=fake_caller)
        assert result["answer"] == "A generated answer."
        assert result["mode"] == "generative"
        assert captured["args"][0] == "https://api.example.com"
        assert captured["args"][1] == "secret"
        assert captured["args"][3] == "What is 2+2?"

    def test_ask_generative_falls_back_to_predefined_when_caller_raises(self):
        self.engine.configure_generative_mode("npc-1", "char-1", api_base_url="https://api.example.com", api_key="secret")

        def failing_caller(*args):
            raise RuntimeError("upstream API is down")

        result = self.engine.ask_generative("npc-1", "char-1", "What is 2+2?", caller=failing_caller)
        assert result["mode"] == "predefined"
        assert result["answer"]

    def test_ask_generative_is_rate_limited_per_user_after_default_max_requests(self):
        self.engine.configure_generative_mode("npc-1", "char-1", api_base_url="https://api.example.com", api_key="secret")
        caller = lambda *a: "A generated answer."

        for i in range(5):
            result = self.engine.ask_generative(
                "npc-1", "char-1", "hint?", caller=caller, user_id="p1", now_ms=i,
            )
            assert result["mode"] == "generative"

        blocked = self.engine.ask_generative(
            "npc-1", "char-1", "hint?", caller=caller, user_id="p1", now_ms=5,
        )
        assert blocked["mode"] == "rate_limited"
        assert blocked["answer"]

    def test_ask_generative_rate_limit_is_tracked_per_user(self):
        self.engine.configure_generative_mode("npc-1", "char-1", api_base_url="https://api.example.com", api_key="secret")
        caller = lambda *a: "A generated answer."

        for i in range(5):
            self.engine.ask_generative("npc-1", "char-1", "hint?", caller=caller, user_id="p1", now_ms=i)
        # A different user should not be affected by p1's rate limit.
        result = self.engine.ask_generative("npc-1", "char-1", "hint?", caller=caller, user_id="p2", now_ms=5)
        assert result["mode"] == "generative"

    def test_ask_generative_rate_limit_resets_after_window_elapses(self):
        self.engine.configure_generative_mode("npc-1", "char-1", api_base_url="https://api.example.com", api_key="secret")
        caller = lambda *a: "A generated answer."

        for i in range(5):
            self.engine.ask_generative("npc-1", "char-1", "hint?", caller=caller, user_id="p1", now_ms=i)
        blocked = self.engine.ask_generative("npc-1", "char-1", "hint?", caller=caller, user_id="p1", now_ms=5)
        assert blocked["mode"] == "rate_limited"

        later = self.engine.ask_generative(
            "npc-1", "char-1", "hint?", caller=caller, user_id="p1", now_ms=60_001,
        )
        assert later["mode"] == "generative"

    def test_ask_generative_skips_rate_limiting_without_user_id(self):
        self.engine.configure_generative_mode("npc-1", "char-1", api_base_url="https://api.example.com", api_key="secret")
        caller = lambda *a: "A generated answer."

        for _ in range(10):
            result = self.engine.ask_generative("npc-1", "char-1", "hint?", caller=caller)
            assert result["mode"] == "generative"
