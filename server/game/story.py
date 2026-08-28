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

from pydantic import BaseModel, ConfigDict, Field, field_validator

from server.game.avatar import create_default_character_appearance, validate_character_appearance
from server.game.rate_limiter import SlidingWindowRateLimiter
from server.game.url_safety import is_safe_external_url

ALLOWED_ROLES = {"guide", "quiz_master", "narrator", "historical_persona", "mentor"}

# An `ai_character` room object is provisioned with this placeholder profile
# the moment it is placed, so that appearance/knowledge/generative editing
# works immediately instead of failing until the author happens to press
# "Save Character" first.
DEFAULT_CHARACTER_NAME = "New Character"
DEFAULT_CHARACTER_ROLE = "guide"
DEFAULT_CHARACTER_START_NODE_ID = "start"

_FALLBACK_ANSWER = "I'm not sure about that yet, but let's continue our story."
_RATE_LIMITED_ANSWER = "You're asking questions a bit too fast — please wait a moment and try again."

# Section 22.3: a character's knowledge base is a small document store (not
# a single free-text blob), so a story author can organize multiple
# text/markdown snippets and reference links. Capped to keep the combined
# prompt sent to a room-admin-configured external API bounded in size/cost.
KNOWLEDGE_DOC_TYPES = {"text", "markdown", "link"}
MAX_KNOWLEDGE_DOCUMENTS = 20
MAX_KNOWLEDGE_DOC_CONTENT_LENGTH = 4000
MAX_KNOWLEDGE_BASE_TITLE_LENGTH = 120
MAX_KNOWLEDGE_CONTEXT_LENGTH = 6000

# Phase J abuse protection: cap generative (paid/third-party) requests per
# user per character to a small burst per minute. Predefined-mode talk/hint
# flows are unaffected — only actual generative API calls are throttled.
GENERATIVE_RATE_LIMIT_MAX_REQUESTS = 5
GENERATIVE_RATE_LIMIT_WINDOW_MS = 60_000.0


class StoryChoiceModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(min_length=1, max_length=200)
    next_node_id: str | None = Field(default=None, alias="nextNodeId")


class KnowledgeDocumentModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(min_length=1, max_length=120)
    doc_type: str = Field(alias="docType")
    content: str | None = Field(default=None, max_length=MAX_KNOWLEDGE_DOC_CONTENT_LENGTH)
    url: str | None = Field(default=None, max_length=2000)

    @field_validator("doc_type")
    @classmethod
    def _validate_doc_type(cls, value: str) -> str:
        if value not in KNOWLEDGE_DOC_TYPES:
            raise ValueError(f"docType must be one of {sorted(KNOWLEDGE_DOC_TYPES)}, got {value!r}")
        return value


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
        self._generative_rate_limiter = SlidingWindowRateLimiter(
            max_requests=GENERATIVE_RATE_LIMIT_MAX_REQUESTS, window_ms=GENERATIVE_RATE_LIMIT_WINDOW_MS,
        )

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
            "appearance": create_default_character_appearance(),
            "knowledgeBase": {"title": None, "documents": [], "updatedAt": None},
            "generativeEnabled": False,
            "apiBaseUrl": None,
            "apiKey": None,
        }
        characters[character_id] = record
        return self._public_character(record)

    def set_character_profile(
        self, object_id: str, character_id: str, name: str, role: str, start_node_id: str,
        portrait_url: str | None = None,
    ) -> dict[str, Any]:
        """Updates an existing character's authored profile in place. Unlike
        `add_character` this preserves everything the author configured
        separately -- appearance, knowledge base, and generative settings --
        so renaming a character never silently resets its look or content."""
        record = self._require_character(object_id, character_id)
        if role not in ALLOWED_ROLES:
            raise ValueError(f"invalid role: {role}")
        if not name or not name.strip():
            raise ValueError("name is required")
        record["name"] = name
        record["role"] = role
        record["startNodeId"] = start_node_id
        record["portraitUrl"] = portrait_url
        return self._public_character(record)

    def set_character_appearance(
        self, object_id: str, character_id: str, appearance: dict[str, Any],
    ) -> dict[str, Any]:
        """Partially updates an AI character's appearance (skin color, body
        type/gender, hair, clothes, accessory, ...), reusing the same option
        set/shape as player avatars so AI characters can be rendered with
        the same avatar renderer. Unknown keys are ignored; the merged
        result must still be a fully valid appearance."""
        record = self._require_character(object_id, character_id)
        merged = {**record["appearance"], **{
            key: value for key, value in appearance.items()
            if key in record["appearance"] and value is not None
        }}
        if not validate_character_appearance(merged):
            raise ValueError("invalid character appearance")
        record["appearance"] = merged
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

    def set_knowledge_base_title(
        self, object_id: str, character_id: str, title: str | None, now_ms: float = 0.0,
    ) -> dict[str, Any]:
        record = self._require_character(object_id, character_id)
        if title is not None:
            title = title.strip() or None
        if title and len(title) > MAX_KNOWLEDGE_BASE_TITLE_LENGTH:
            raise ValueError(f"title must be {MAX_KNOWLEDGE_BASE_TITLE_LENGTH} characters or fewer")
        record["knowledgeBase"]["title"] = title
        record["knowledgeBase"]["updatedAt"] = now_ms
        return self._public_character(record)

    def add_knowledge_document(
        self, object_id: str, character_id: str, doc_id: str, title: str, doc_type: str,
        content: str | None = None, url: str | None = None, now_ms: float = 0.0,
    ) -> dict[str, Any]:
        record = self._require_character(object_id, character_id)
        documents = record["knowledgeBase"]["documents"]
        if len(documents) >= MAX_KNOWLEDGE_DOCUMENTS:
            raise ValueError(f"knowledge base cannot exceed {MAX_KNOWLEDGE_DOCUMENTS} documents")
        if any(d["docId"] == doc_id for d in documents):
            raise ValueError(f"document id already exists: {doc_id}")
        validated = KnowledgeDocumentModel(title=title, docType=doc_type, content=content, url=url)
        if validated.doc_type == "link":
            if not validated.url or not is_safe_external_url(validated.url):
                raise ValueError("link documents require a safe http(s) url")
        elif not validated.content or not validated.content.strip():
            raise ValueError(f"{validated.doc_type} documents require non-empty content")
        doc = {
            "docId": doc_id, "title": validated.title, "docType": validated.doc_type,
            "content": validated.content, "url": validated.url,
        }
        documents.append(doc)
        record["knowledgeBase"]["updatedAt"] = now_ms
        return self._public_character(record)

    def remove_knowledge_document(
        self, object_id: str, character_id: str, doc_id: str, now_ms: float = 0.0,
    ) -> dict[str, Any]:
        record = self._require_character(object_id, character_id)
        documents = record["knowledgeBase"]["documents"]
        remaining = [d for d in documents if d["docId"] != doc_id]
        if len(remaining) == len(documents):
            raise KeyError(f"unknown knowledge document: {doc_id}")
        record["knowledgeBase"]["documents"] = remaining
        record["knowledgeBase"]["updatedAt"] = now_ms
        return self._public_character(record)

    def update_knowledge_document(
        self, object_id: str, character_id: str, doc_id: str, title: str, doc_type: str,
        content: str | None = None, url: str | None = None, now_ms: float = 0.0,
    ) -> dict[str, Any]:
        record = self._require_character(object_id, character_id)
        documents = record["knowledgeBase"]["documents"]
        index = next((i for i, d in enumerate(documents) if d["docId"] == doc_id), None)
        if index is None:
            raise KeyError(f"unknown knowledge document: {doc_id}")
        validated = KnowledgeDocumentModel(title=title, docType=doc_type, content=content, url=url)
        if validated.doc_type == "link":
            if not validated.url or not is_safe_external_url(validated.url):
                raise ValueError("link documents require a safe http(s) url")
        elif not validated.content or not validated.content.strip():
            raise ValueError(f"{validated.doc_type} documents require non-empty content")
        documents[index] = {
            "docId": doc_id, "title": validated.title, "docType": validated.doc_type,
            "content": validated.content, "url": validated.url,
        }
        record["knowledgeBase"]["updatedAt"] = now_ms
        return self._public_character(record)

    def list_knowledge_documents(self, object_id: str, character_id: str) -> list[dict[str, Any]]:
        record = self._require_character(object_id, character_id)
        return [dict(d) for d in record["knowledgeBase"]["documents"]]

    def move_knowledge_document(
        self, object_id: str, character_id: str, doc_id: str, direction: str, now_ms: float = 0.0,
    ) -> dict[str, Any]:
        if direction not in ("up", "down"):
            raise ValueError("direction must be 'up' or 'down'")
        record = self._require_character(object_id, character_id)
        documents = record["knowledgeBase"]["documents"]
        index = next((i for i, d in enumerate(documents) if d["docId"] == doc_id), None)
        if index is None:
            raise KeyError(f"unknown knowledge document: {doc_id}")
        target = index - 1 if direction == "up" else index + 1
        if 0 <= target < len(documents):
            documents[index], documents[target] = documents[target], documents[index]
            record["knowledgeBase"]["updatedAt"] = now_ms
        return self._public_character(record)

    @staticmethod
    def _build_knowledge_context(record: dict[str, Any]) -> str | None:
        """Flatten a character's knowledge store into a single bounded text
        block suitable for use as an LLM system-prompt snippet or as the
        predefined-mode fallback answer. Link documents are included as a
        reference (title + URL) rather than fetched, since fetching
        arbitrary story-author-supplied URLs server-side would reopen the
        SSRF surface `is_safe_external_url` guards against elsewhere."""
        kb = record["knowledgeBase"]
        parts = []
        if kb["title"]:
            parts.append(f"Knowledge base: {kb['title']}")
        for doc in kb["documents"]:
            if doc["docType"] == "link":
                parts.append(f'Reference "{doc["title"]}": {doc["url"]}')
            else:
                parts.append(f"{doc['title']}: {doc['content']}")
        if not parts:
            return None
        return "\n\n".join(parts)[:MAX_KNOWLEDGE_CONTEXT_LENGTH]

    def configure_generative_mode(
        self, object_id: str, character_id: str, api_base_url: str | None = None, api_key: str | None = None,
    ) -> dict[str, Any]:
        record = self._require_character(object_id, character_id)
        if api_base_url and not is_safe_external_url(api_base_url):
            raise ValueError("apiBaseUrl is not a permitted external address")
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
        is_solved: Callable[[str, str], bool] | None = None,
    ) -> dict[str, Any]:
        """`is_solved` (design doc feature_designs/escape_room_feature_design.md
        §6.4) is an optional `(puzzle_id, user_id) -> bool` callback, mirroring
        `ask_generative`'s existing `caller` callback-injection pattern, since
        `StoryEngine` has no direct dependency on `PuzzleEngine`. When the
        current node's `knowledgeCheck` is set and a choice is being made,
        the callback is consulted; if it returns False the choice is blocked
        (progress does not advance) and the response is flagged
        `knowledgeCheckPassed: False` instead of moving to the next node.
        Omitting the callback (e.g. a node with no puzzle-gating configured
        anywhere in the room) never blocks progression, for backward
        compatibility with every pre-existing caller."""
        record = self._require_character(object_id, character_id)
        nodes = self._nodes.get((object_id, character_id), {})
        progress_key = (object_id, character_id, user_id)
        current_node_id = self._progress.get(progress_key, record["startNodeId"])
        current_node = nodes.get(current_node_id)
        if current_node is None:
            raise KeyError(f"story has no node: {current_node_id}")

        if choice_index is not None:
            knowledge_check = current_node.get("knowledgeCheck")
            if knowledge_check is not None and is_solved is not None and not is_solved(knowledge_check, user_id):
                return {
                    "characterId": character_id,
                    "node": dict(current_node),
                    "mode": "generative" if record["generativeEnabled"] else "predefined",
                    "knowledgeCheckPassed": False,
                }

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
        user_id: str | None = None, now_ms: float = 0.0,
    ) -> dict[str, Any]:
        record = self._require_character(object_id, character_id)
        knowledge_context = self._build_knowledge_context(record)
        if not record["generativeEnabled"]:
            return {"answer": self._fallback_answer(knowledge_context), "mode": "predefined"}
        if user_id is not None:
            rate_key = f"{object_id}:{character_id}:{user_id}"
            if not self._generative_rate_limiter.allow(rate_key, now_ms):
                return {"answer": _RATE_LIMITED_ANSWER, "mode": "rate_limited"}
        user_message = (user_message or "")[:200]
        try:
            answer = caller(record["apiBaseUrl"], record["apiKey"], knowledge_context, user_message)
        except Exception:
            return {"answer": self._fallback_answer(knowledge_context), "mode": "predefined"}
        return {"answer": answer, "mode": "generative"}

    @staticmethod
    def _fallback_answer(knowledge_context: str | None) -> str:
        return knowledge_context or _FALLBACK_ANSWER
