"""Phase H: AI story character domain logic.

Predefined, node-based story graph runtime for `ai_character` room objects,
plus an optional generative-answer fallback flow (section 21.5 of the
feature design). Generative mode is gated on a room-admin-configured API
base URL *and* key; the API key is stored server-side only and is never
included in any value returned to callers (client or otherwise), and any
generative call failure transparently falls back to a predefined answer so
the character never "goes silent" from a learner's perspective.
"""

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

ALLOWED_ROLES = {"guide", "quiz_master", "narrator", "historical_persona", "mentor"}

_FALLBACK_ANSWER = "I'm not sure about that yet, but let's continue our story."


class StoryChoiceModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(min_length=1, max_length=200)
    next_node_id: str | None = Field(default=None, alias="nextNodeId")


class StoryNodeModel(BaseModel):
    node_id: str = Field(min_length=1, max_length=64)
    character_line: str = Field(min_length=1, max_length=2000)
    choices: list[StoryChoiceModel] = Field(default_factory=list)
    completion_flag: bool = False
    knowledge_check: str | None = None


class StoryEngine:
    """In-memory per-object AI story characters, story graphs, and per-user
    story progress."""

    def __init__(self) -> None:
        self._characters: dict[str, dict[str, dict[str, Any]]] = {}
        self._nodes: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
        self._progress: dict[tuple[str, str, str], str] = {}

    # ─── Character placement and role ──────────────────────────────────

    def add_character(
        self, object_id: str, character_id: str, name: str, role: str, start_node_id: str,
        portrait_url: str | None = None,
    ) -> dict[str, Any]:
        if role not in ALLOWED_ROLES:
            raise ValueError(f"invalid role: {role}")
        if not name or not name.strip():
            raise ValueError("name is required")
        characters = self._characters.setdefault(object_id, {})
        if character_id in characters:
            raise ValueError(f"character id already exists on this object: {character_id}")
        record = {
            "characterId": character_id,
            "name": name,
            "role": role,
            "portraitUrl": portrait_url,
            "startNodeId": start_node_id,
            "knowledgeBase": None,
            "generativeEnabled": False,
            "apiBaseUrl": None,
            "apiKey": None,
        }
        characters[character_id] = record
        return self._public_character(record)

    def list_characters(self, object_id: str) -> list[dict[str, Any]]:
        return [self._public_character(r) for r in self._characters.get(object_id, {}).values()]

    def get_character(self, object_id: str, character_id: str) -> dict[str, Any] | None:
        record = self._characters.get(object_id, {}).get(character_id)
        return self._public_character(record) if record else None

    def remove_character(self, object_id: str, character_id: str) -> bool:
        characters = self._characters.get(object_id, {})
        if character_id not in characters:
            return False
        del characters[character_id]
        self._nodes.pop((object_id, character_id), None)
        stale_progress_keys = [
            key for key in self._progress if key[0] == object_id and key[1] == character_id
        ]
        for key in stale_progress_keys:
            del self._progress[key]
        return True

    def _require_character(self, object_id: str, character_id: str) -> dict[str, Any]:
        record = self._characters.get(object_id, {}).get(character_id)
        if record is None:
            raise KeyError(f"unknown character: {character_id}")
        return record

    @staticmethod
    def _public_character(record: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in record.items() if key != "apiKey"}

    # ─── Knowledge base and generative-mode configuration ──────────────

    def set_knowledge_base(self, object_id: str, character_id: str, content: str) -> dict[str, Any]:
        record = self._require_character(object_id, character_id)
        record["knowledgeBase"] = content
        return self._public_character(record)

    def configure_generative_mode(
        self, object_id: str, character_id: str, api_base_url: str | None = None, api_key: str | None = None,
    ) -> dict[str, Any]:
        record = self._require_character(object_id, character_id)
        record["apiBaseUrl"] = api_base_url
        record["apiKey"] = api_key
        record["generativeEnabled"] = bool(api_base_url and api_key)
        return self._public_character(record)

    # ─── Predefined story graph ─────────────────────────────────────────

    def add_story_node(
        self, object_id: str, character_id: str, node_id: str, character_line: str,
        choices: list[dict[str, Any]] | None = None, completion_flag: bool = False,
        knowledge_check: str | None = None,
    ) -> dict[str, Any]:
        self._require_character(object_id, character_id)
        validated = StoryNodeModel(
            node_id=node_id, character_line=character_line, choices=choices or [],
            completion_flag=completion_flag, knowledge_check=knowledge_check,
        )
        node = {
            "nodeId": validated.node_id,
            "characterLine": validated.character_line,
            "choices": [{"text": c.text, "nextNodeId": c.next_node_id} for c in validated.choices],
            "completionFlag": validated.completion_flag,
            "knowledgeCheck": validated.knowledge_check,
        }
        self._nodes.setdefault((object_id, character_id), {})[node_id] = node
        return dict(node)

    def get_story_node(self, object_id: str, character_id: str, node_id: str) -> dict[str, Any] | None:
        self._require_character(object_id, character_id)
        node = self._nodes.get((object_id, character_id), {}).get(node_id)
        return dict(node) if node else None

    def list_story_nodes(self, object_id: str, character_id: str) -> list[dict[str, Any]]:
        self._require_character(object_id, character_id)
        return [dict(n) for n in self._nodes.get((object_id, character_id), {}).values()]

    # ─── Predefined story runtime (talk / choices / progress) ──────────

    def talk(
        self, object_id: str, character_id: str, user_id: str, choice_index: int | None = None,
    ) -> dict[str, Any]:
        record = self._require_character(object_id, character_id)
        nodes = self._nodes.get((object_id, character_id), {})
        progress_key = (object_id, character_id, user_id)
        current_node_id = self._progress.get(progress_key, record["startNodeId"])
        current_node = nodes.get(current_node_id)
        if current_node is None:
            raise KeyError(f"story has no node: {current_node_id}")

        if choice_index is not None:
            choices = current_node["choices"]
            if choice_index < 0 or choice_index >= len(choices):
                raise ValueError("invalid choice index")
            next_node_id = choices[choice_index]["nextNodeId"]
            if next_node_id is not None:
                if next_node_id not in nodes:
                    raise KeyError(f"story has no node: {next_node_id}")
                current_node_id = next_node_id
                current_node = nodes[current_node_id]
            self._progress[progress_key] = current_node_id

        return {
            "characterId": character_id,
            "node": dict(current_node),
            "mode": "generative" if record["generativeEnabled"] else "predefined",
        }

    def restart_story(self, object_id: str, character_id: str, user_id: str) -> dict[str, Any]:
        record = self._require_character(object_id, character_id)
        self._progress[(object_id, character_id, user_id)] = record["startNodeId"]
        return self.talk(object_id, character_id, user_id)

    # ─── Optional generative-mode fallback flow ────────────────────────

    def ask_generative(
        self, object_id: str, character_id: str, user_message: str,
        caller: Callable[[str, str, str | None, str], str],
    ) -> dict[str, Any]:
        record = self._require_character(object_id, character_id)
        if not record["generativeEnabled"]:
            return {"answer": self._fallback_answer(record), "mode": "predefined"}
        try:
            answer = caller(record["apiBaseUrl"], record["apiKey"], record["knowledgeBase"], user_message)
        except Exception:
            return {"answer": self._fallback_answer(record), "mode": "predefined"}
        return {"answer": answer, "mode": "generative"}

    @staticmethod
    def _fallback_answer(record: dict[str, Any]) -> str:
        return record["knowledgeBase"] or _FALLBACK_ANSWER
