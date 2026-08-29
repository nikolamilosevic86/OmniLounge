"""Escape room feature, Phase 3: puzzle template library.

Design: feature_designs/escape_room_feature_design.md §14 Phase 3
("Puzzle template library (pre-built riddle/cipher/sequence puzzle types
with built-in `match_mode` presets)"), resolving §16 Q5's deferral.

A pure, data-only catalog in the same spirit as `room_object_catalog.py`:
no I/O, no engine state, fully unit-testable. Its whole job is authoring
convenience -- a creator picks an archetype and gets a starter prompt,
starter hints and, most importantly, the `match_mode` that archetype
actually needs, instead of having to reason about why a number-lock
answer of "7" would otherwise reject a guess of "007".

Templates deliberately add no new concepts to `PuzzleEngine`:
`build_puzzle_from_template` resolves down to the exact keyword arguments
`PuzzleEngine.add_puzzle` already accepts, so a templated puzzle and a
hand-authored one are indistinguishable once created.
"""

import copy
from typing import Any

PUZZLE_TEMPLATES: dict[str, dict[str, Any]] = {
    "riddle": {
        "label": "Riddle",
        "description": "A word riddle with a single specific answer.",
        "promptTemplate": "I have keys but open no locks. I have space but no room. What am I?",
        "answerPlaceholder": "a keyboard",
        "matchMode": "exact",
        "propType": "riddle_tablet",
        "hints": [
            "You use it every day.",
            "It sits on a desk.",
        ],
    },
    "cipher": {
        "label": "Cipher",
        "description": "A coded message the player must decode into plain text.",
        "promptTemplate": (
            "Decode this message (each letter is shifted forward by one): "
            "SFE EPPS"
        ),
        "answerPlaceholder": "red door",
        "matchMode": "exact",
        "propType": "cipher_box",
        "hints": [
            "Every letter moved one step through the alphabet.",
            "Shift each letter back by one to read it.",
        ],
    },
    "sequence": {
        "label": "Sequence",
        "description": "A number or symbol pattern where the player supplies the next term.",
        "promptTemplate": "What number comes next? 2, 4, 8, 16, ...",
        "answerPlaceholder": "32",
        "matchMode": "numeric",
        "propType": "combination_dial",
        "hints": [
            "Look at what happens from one number to the next.",
            "Each number is double the one before it.",
        ],
    },
    "number_lock": {
        "label": "Number Lock",
        "description": "A numeric combination the player collects from clues around the room.",
        "promptTemplate": "Enter the 4-digit combination.",
        "answerPlaceholder": "1234",
        # `numeric` so leading zeros / stray whitespace in a typed combination
        # still match the authored answer.
        "matchMode": "numeric",
        "propType": "digital_lock",
        "hints": [
            "The digits are hidden on objects around the room.",
            "Read them in the order the room's story suggests.",
        ],
    },
    "keyword_search": {
        "label": "Keyword Search",
        "description": "The player must mention a key word or phrase they found while exploring.",
        "promptTemplate": "What word was written on the note?",
        "answerPlaceholder": "lighthouse",
        # `contains` so a player who types a full sentence containing the
        # keyword still passes -- this archetype rewards finding the fact,
        # not phrasing it precisely.
        "matchMode": "contains",
        "propType": "clue_board",
        "hints": [
            "Search the room for something with writing on it.",
            "Only one word matters -- the rest is decoration.",
        ],
    },
}


def list_templates() -> list[dict[str, Any]]:
    """Every template, deep-copied so a caller (or a socket handler
    serializing them to a client) can never mutate the catalog itself."""
    return [get_template(template_id) for template_id in PUZZLE_TEMPLATES]


def get_template(template_id: str) -> dict[str, Any]:
    record = PUZZLE_TEMPLATES.get(template_id)
    if record is None:
        raise KeyError(f"unknown puzzle template: {template_id}")
    return {"templateId": template_id, **copy.deepcopy(record)}


def build_puzzle_from_template(
    template_id: str,
    answer: str,
    prompt: str | None = None,
    hints: list[str] | None = None,
    match_mode: str | None = None,
    prop_type: str | None = None,
) -> dict[str, Any]:
    """Resolve a template plus the creator's own answer into
    `PuzzleEngine.add_puzzle` keyword arguments.

    The template supplies defaults only: any explicitly provided `prompt`,
    `hints`, `match_mode` or `prop_type` wins, so a preset is a smart
    starting point rather than a cage. Note `hints` falls back to the
    template's list only when it is `None` -- passing `[]` explicitly means
    "no hints".
    """
    template = get_template(template_id)
    if not answer or not answer.strip():
        raise ValueError("answer is required")
    return {
        "prompt": prompt if prompt is not None else template["promptTemplate"],
        "answer": answer,
        "hints": list(hints) if hints is not None else list(template["hints"]),
        "match_mode": match_mode if match_mode is not None else template["matchMode"],
        "prop_type": prop_type if prop_type is not None else template["propType"],
    }
