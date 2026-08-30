"""Two showcase rooms that exist from the moment the server boots.

Rooms live in memory only (`RoomsRegistry`), so a fresh process starts with
nothing but an empty Lobby -- which makes for a poor first impression and
leaves every builder feature (books, video, music, AI characters, puzzles,
escape sessions, multi-tile navigation) undiscovered unless a visitor
happens to build it themselves.

These two seeded rooms are the guided answer to "what can this thing do?":

  * `leonardo-workshop` -- an educational Renaissance room about Leonardo
    da Vinci. Exercises the bookshelf, TV, music player and AI-character
    (knowledge base + branching story + guided tour) systems.
  * `alchemist-vault`   -- a timed escape room. Exercises the puzzle
    engine (all three match modes and all five prop shapes), hidden items,
    an escape door gated on puzzles, and the escape-session timer.

Because seeding runs on every boot, everything here must be idempotent at
the room level: `seed_showcase_rooms` is a no-op if the rooms already
exist. All biographical facts below are drawn from the Wikipedia article
on Leonardo da Vinci; the YouTube ids were verified against the oEmbed API
at authoring time.
"""

from typing import Any

from server.game.rooms_registry import RoomsRegistry

# Both rooms are owned by the same synthetic host as the Lobby. Nobody can
# connect as "system", so the rooms are effectively read-only to visitors
# while still letting the seeding code below author them as room host.
SEED_HOST_ID = "system"

EDUCATIONAL_ROOM_ID = "leonardo-workshop"
ESCAPE_ROOM_ID = "alchemist-vault"

# 20 minutes: long enough to read the clues and talk to the character,
# short enough that a failed run is worth retrying.
ESCAPE_TIME_LIMIT_MS = 20 * 60 * 1000.0

# Verified YouTube video ids (each returned a real title/author from
# https://www.youtube.com/oembed at the time this module was written).
VIDEO_DECODING_DA_VINCI = "NGsUFvwgvCo"
VIDEO_RENAISSANCE_MAN = "ROTsA2-2b7Q"
VIDEO_FLYING_MACHINES = "Y0_htkvCVpE"
VIDEO_MONA_LISA = "0yWzmtLI9tY"
TRACK_ITALIAN_LUTE = "I2q7br9-T9g"
TRACK_JOSQUIN_MISERERE = "DkL1cOdpTYo"
TRACK_JOSQUIN_AVE_MARIA = "LUAgAF4Khmg"
TRACK_MEDIEVAL_SEA = "2szGfDkrsvU"
TRACK_1500S_SONG = "pgDbj2OvSwI"


def seed_showcase_rooms(registry: RoomsRegistry) -> list[str]:
    """Creates the two demo rooms if they are not already present.

    Returns the ids of the rooms that were actually created, so a caller
    can log what happened on boot.
    """
    created: list[str] = []
    if EDUCATIONAL_ROOM_ID not in registry.rooms:
        _seed_leonardo_workshop(registry)
        created.append(EDUCATIONAL_ROOM_ID)
    if ESCAPE_ROOM_ID not in registry.rooms:
        _seed_alchemist_vault(registry)
        created.append(ESCAPE_ROOM_ID)
    return created


def _create_seed_room(
    registry: RoomsRegistry, room_id: str, name: str, topic_tags: list[str], room_style: str,
    max_users: int,
) -> None:
    """`create_room` mints its own sequential `room-NNNN` id, but these two
    rooms need stable, human-readable ids (they are linked to from the docs
    and asserted on in tests). So create through the registry and then
    re-key the entry under the id we want."""
    meta = registry.create_room(
        SEED_HOST_ID, name, topic_tags=topic_tags, access="public",
        max_users=max_users, room_style=room_style,
    )
    generated_id = meta["id"]
    for store in (
        registry.rooms, registry.room_meta, registry.room_tiles,
        registry.room_builders, registry.room_moderation,
    ):
        store[room_id] = store.pop(generated_id)
    registry.rooms[room_id].id = room_id
    registry.room_meta[room_id]["id"] = room_id


# ─────────────────────────── Educational room ───────────────────────────


def _seed_leonardo_workshop(registry: RoomsRegistry) -> None:
    _create_seed_room(
        registry, EDUCATIONAL_ROOM_ID,
        name="Leonardo's Workshop",
        topic_tags=["education", "history", "art", "renaissance"],
        room_style="renaissance-studio",
        max_users=60,
    )
    builder = registry.get_builder(EDUCATIONAL_ROOM_ID)
    assert builder is not None

    # Three tiles: the bottega itself, a library to its right, and a
    # "hall of inventions" above it -- so visitors immediately discover
    # that rooms are multi-screen.
    registry.add_neighbor_tile(EDUCATIONAL_ROOM_ID, (0, 0), "right")
    registry.add_neighbor_tile(EDUCATIONAL_ROOM_ID, (0, 0), "top")
    builder.configure_tile((0, 0), label="The Bottega", purpose_tag="social")
    builder.configure_tile((1, 0), label="Library & Codices", purpose_tag="quiet")
    builder.configure_tile((0, -1), label="Hall of Inventions", purpose_tag="exhibit")

    _seed_workshop_furniture(builder)
    _seed_workshop_bookshelf(builder)
    _seed_workshop_media(builder)
    _seed_leonardo_character(builder)


def _seed_workshop_furniture(builder: Any) -> None:
    host = {"requester_id": SEED_HOST_ID, "is_room_host": True}
    # A master's worktable with stools, in dark walnut and oak -- the
    # colour presets are what carry the "Renaissance" read on the sprites.
    builder.create_object(
        "lw-worktable", "table", (0, 0), 400.0, 330.0, size_preset="L",
        color="dark-wood", material="wood", created_by=SEED_HOST_ID,
    )
    for index, (x, y) in enumerate(((300.0, 300.0), (500.0, 300.0), (400.0, 430.0))):
        builder.create_object(
            f"lw-stool-{index}", "chair", (0, 0), x, y, size_preset="S",
            color="natural-wood", material="wood", created_by=SEED_HOST_ID,
        )
    # A long refectory bench along the wall for visitors to sit and talk.
    builder.create_object(
        "lw-bench", "sofa", (0, 0), 150.0, 460.0, size_preset="L",
        color="burgundy", material="fabric", created_by=SEED_HOST_ID,
    )
    builder.create_object(
        "lw-reading-couch", "sofa", (1, 0), 200.0, 420.0, size_preset="L",
        color="dark-wood", material="fabric", created_by=SEED_HOST_ID,
    )
    builder.create_object(
        "lw-study-table", "table", (1, 0), 560.0, 400.0, size_preset="M",
        color="dark-wood", material="wood", created_by=SEED_HOST_ID,
    )
    builder.create_object(
        "lw-study-chair", "chair", (1, 0), 560.0, 490.0, size_preset="S",
        color="natural-wood", material="wood", created_by=SEED_HOST_ID,
    )
    # Hall of inventions: plinths (tables) standing in for the models
    # Leonardo built or drew, plus a clue board of his own notes.
    for index, x in enumerate((200.0, 400.0, 600.0)):
        builder.create_object(
            f"lw-plinth-{index}", "table", (0, -1), x, 380.0, size_preset="M",
            color="gold-accent", material="stone", created_by=SEED_HOST_ID,
        )
    builder.create_object(
        "lw-notes-board", "clue_board", (0, -1), 400.0, 180.0, size_preset="L",
        color="natural-wood", material="wood", created_by=SEED_HOST_ID,
        config={
            "note": (
                "From the notebooks: 'Il sole non si muove' -- The Sun does not move. "
                "Some 13,000 pages survive, written right-to-left in mirror script."
            ),
        },
    )


def _seed_workshop_bookshelf(builder: Any) -> None:
    host = {"requester_id": SEED_HOST_ID, "is_room_host": True}
    builder.create_object(
        "lw-bookshelf", "bookshelf", (1, 0), 400.0, 200.0, size_preset="L",
        color="dark-wood", material="wood", created_by=SEED_HOST_ID,
    )
    for book in _LEONARDO_BOOKS:
        builder.add_book(
            "lw-bookshelf", book["book_id"], book["title"], book["content_body"],
            author=book.get("author", "Curator's note"),
            summary=book.get("summary"),
            reading_level=book.get("reading_level", "general"),
            est_read_minutes=book.get("est_read_minutes", 3),
            **host,
        )


def _seed_workshop_media(builder: Any) -> None:
    host = {"requester_id": SEED_HOST_ID, "is_room_host": True}
    builder.create_object(
        "lw-screen", "tv", (0, -1), 400.0, 90.0, size_preset="L",
        color="gold-accent", material="wood", created_by=SEED_HOST_ID,
    )
    builder.add_video(
        "lw-screen", "vid-decoding", "Decoding da Vinci (NOVA, PBS)",
        VIDEO_DECODING_DA_VINCI,
        description="Feature documentary on how Leonardo's science shaped his painting.",
        **host,
    )
    builder.add_video(
        "lw-screen", "vid-renaissance-man", "Leonardo da Vinci: The Renaissance Man",
        VIDEO_RENAISSANCE_MAN,
        description="Full biographical documentary from The People Profiles.",
        **host,
    )
    builder.add_video(
        "lw-screen", "vid-flying-machines", "Leonardo da Vinci's Flying Machines",
        VIDEO_FLYING_MACHINES,
        description="Short explainer on the ornithopter and the aerial screw.",
        **host,
    )
    builder.add_video(
        "lw-screen", "vid-mona-lisa", "The Mona Lisa: A Two-Minute Louvre History",
        VIDEO_MONA_LISA,
        description="Why the portrait of Lisa del Giocondo became the most visited painting on earth.",
        **host,
    )

    builder.create_object(
        "lw-consort", "music_player", (0, 0), 660.0, 220.0, size_preset="M",
        color="dark-wood", material="wood", created_by=SEED_HOST_ID,
    )
    builder.add_track(
        "lw-consort", "trk-lute", "The Italian Lute", TRACK_ITALIAN_LUTE,
        artist="Brilliant Classics", **host,
    )
    builder.add_track(
        "lw-consort", "trk-miserere", "Miserere mei, Deus", TRACK_JOSQUIN_MISERERE,
        artist="Josquin des Prez / Magnificat", **host,
    )
    builder.add_track(
        "lw-consort", "trk-ave-maria", "Ave Maria", TRACK_JOSQUIN_AVE_MARIA,
        artist="Josquin des Prez", **host,
    )
    builder.add_track(
        "lw-consort", "trk-medieval-sea", "Medieval Music by the Sea", TRACK_MEDIEVAL_SEA,
        artist="Medieval Music Online", **host,
    )


def _seed_leonardo_character(builder: Any) -> None:
    host = {"requester_id": SEED_HOST_ID, "is_room_host": True}
    builder.create_object(
        "lw-leonardo", "ai_character", (0, 0), 620.0, 400.0,
        color="burgundy", material="fabric", created_by=SEED_HOST_ID,
    )
    builder.configure_character(
        "lw-leonardo", "Leonardo da Vinci", "historical_persona", "intro", **host,
    )
    builder.configure_character_appearance(
        "lw-leonardo",
        {
            "skinColor": "#F1C27D",
            "gender": "masculine",
            "hair": "long",
            "beard": "full",
            "glasses": "none",
            "clothes": "jacket",
            "accessory": "hat",
        },
        **host,
    )
    builder.set_character_knowledge_base_title(
        "lw-leonardo", "The life and notebooks of Leonardo da Vinci", **host,
    )
    for doc in _LEONARDO_KNOWLEDGE:
        builder.add_character_knowledge_document(
            "lw-leonardo", doc["doc_id"], doc["title"], doc["doc_type"],
            content=doc.get("content"), url=doc.get("url"), **host,
        )
    for node in _LEONARDO_STORY_NODES:
        builder.add_story_node(
            "lw-leonardo", node["node_id"], node["character_line"],
            choices=node.get("choices"), completion_flag=node.get("completion_flag", False),
            **host,
        )
    # "Follow me" tour around the bottega tile.
    for waypoint in (
        ("wp-table", 400.0, 330.0, "The worktable"),
        ("wp-music", 640.0, 250.0, "The consort of instruments"),
        ("wp-bench", 180.0, 450.0, "The refectory bench"),
        ("wp-door", 400.0, 540.0, "Onward to the library"),
    ):
        builder.add_character_waypoint("lw-leonardo", waypoint[0], waypoint[1], waypoint[2], label=waypoint[3], **host)


_LEONARDO_BOOKS: list[dict[str, Any]] = [
    {
        "book_id": "bk-early-life",
        "title": "Vinci, 1452: An Illegitimate Beginning",
        "author": "Curator's note",
        "summary": "Birth, family, and the road to Florence.",
        "content_body": (
            "Leonardo was born on 15 April 1452 in, or near, the Tuscan hill town of Vinci, "
            "roughly 35 kilometres from Florence. He was born out of wedlock to Ser Piero da "
            "Vinci, a Florentine notary, and a young woman named Caterina di Meo Lippi. Between "
            "his father's four marriages and his mother's own family, he eventually had some "
            "sixteen half-siblings, most of them very much younger than he was.\n\n"
            "Illegitimacy closed some doors and opened others. He could not follow his father "
            "into the notarial profession or attend a university, so he was never given the "
            "standard Latin-and-Greek education of a gentleman. He later described himself, with "
            "an edge of defiance, as an unlettered man. What he had instead was the countryside: "
            "water, rocks, birds, plants, and light, all of which he studied for the rest of his "
            "life with the attention other men gave to books.\n\n"
            "At around fourteen he entered Florence as a garzone -- a studio boy -- in the "
            "workshop of Andrea del Verrocchio, one of the most successful bottegas in the city."
        ),
    },
    {
        "book_id": "bk-verrocchio",
        "title": "The Bottega: Apprenticeship Under Verrocchio",
        "author": "Curator's note",
        "summary": "Seven years of training, and the angel that outshone the master.",
        "content_body": (
            "Leonardo was formally an apprentice by the age of seventeen and trained in "
            "Verrocchio's workshop for about seven years. A Florentine bottega was not an art "
            "school in the modern sense; it was a business that produced altarpieces, bronzes, "
            "armour, pageant machinery and metalwork alike. An apprentice learned drafting, "
            "chemistry, metallurgy, carpentry, plaster casting and leather working as a matter "
            "of course.\n\n"
            "The most famous product of the collaboration is 'The Baptism of Christ' (c. 1472-75), "
            "now in the Uffizi. Leonardo painted the kneeling angel at the left, and the passage "
            "is so much softer and more atmospheric than the surrounding figures that Vasari "
            "later claimed Verrocchio put down his brush and never painted again.\n\n"
            "In 1472, aged twenty, Leonardo qualified as a master in the Guild of Saint Luke. His "
            "earliest surviving dated work is a pen-and-ink drawing of the Arno valley, inscribed "
            "1473 -- a landscape drawn for its own sake, which was itself an unusual idea."
        ),
    },
    {
        "book_id": "bk-milan",
        "title": "Milan, 1482-1499: Engineer to the Sforza Court",
        "author": "Curator's note",
        "summary": "The Last Supper, the Gran Cavallo, and a job application about weapons.",
        "content_body": (
            "Leonardo left Florence for Milan around 1482 to work for Ludovico Sforza. The letter "
            "he wrote to secure the position is revealing: it advertises portable bridges, siege "
            "engines, covered chariots and cannon at length, and mentions painting and sculpture "
            "almost as an afterthought. He wanted to be hired as an engineer.\n\n"
            "The Milanese years nevertheless produced some of his greatest paintings: the 'Virgin "
            "of the Rocks', the portrait of Cecilia Gallerani known as 'Lady with an Ermine', the "
            "painted arbour of the Sala delle Asse (1498), and, between about 1495 and 1498, 'The "
            "Last Supper' on the refectory wall of Santa Maria delle Grazie. He also drew the "
            "'Vitruvian Man' around 1490 and studied mathematics under Luca Pacioli, later drawing "
            "the polyhedra for Pacioli's 'Divina proportione'.\n\n"
            "The great unfinished work of the period was the Gran Cavallo, a colossal bronze horse. "
            "Leonardo completed a full-size clay model, but in November 1494 the bronze set aside "
            "for it was sent away to be cast into cannon instead. The horse was never made."
        ),
    },
    {
        "book_id": "bk-mona-lisa",
        "title": "Sfumato and the Mona Lisa",
        "author": "Curator's note",
        "summary": "Smoke without lines: the technique behind the most famous portrait in the world.",
        "content_body": (
            "Leonardo began the portrait now called the 'Mona Lisa' -- 'La Gioconda' -- in October "
            "1503. The sitter is generally identified as Lisa del Giocondo, the wife of a Florentine "
            "silk merchant. He kept the panel with him for the rest of his life and never delivered it.\n\n"
            "Its softness comes from sfumato, from the Italian for smoke: colours and tones are laid "
            "in translucent glazes so thin that no line or boundary is visible anywhere in the face. "
            "Leonardo described it as blending 'without lines or borders, in the manner of smoke'. "
            "The effect is why the expression seems to change as you move.\n\n"
            "During the same Florentine years he was commissioned to paint 'The Battle of Anghiari' "
            "in the Palazzo Vecchio, with Michelangelo assigned the opposite wall. Leonardo's mural "
            "failed and is lost; it survives only through copies, the best known by Rubens."
        ),
    },
    {
        "book_id": "bk-notebooks",
        "title": "Thirteen Thousand Pages, Written Backwards",
        "author": "Curator's note",
        "summary": "The codices, the mirror script, and the inventions.",
        "content_body": (
            "About 13,000 pages of Leonardo's notes and drawings survive, bound into codices that "
            "include the Codex Atlanticus, the Codex Arundel and the Codex on the Flight of Birds "
            "(c. 1505). He was left-handed and wrote in mirror-image cursive, right to left, which "
            "is legible only when held up to a glass.\n\n"
            "The pages mix shopping lists with hydraulics, anatomy with jokes. Among the designs are "
            "an ornithopter flying machine (c. 1488), the aerial screw (c. 1489), a parachute, a giant "
            "crossbow, an armoured fighting vehicle, a self-propelled cart, a mechanical knight and a "
            "double-hulled ship.\n\n"
            "Some of the science was centuries early. In 1493 Leonardo stated the laws of sliding "
            "friction, which were not rediscovered until 1699 by Guillaume Amontons; he is named the "
            "first of the twenty-three 'Men of Tribology'."
        ),
    },
    {
        "book_id": "bk-anatomy",
        "title": "The Anatomist of Santa Maria Nuova",
        "author": "Curator's note",
        "summary": "240 drawings, 13,000 words, and a glass model of a heart valve.",
        "content_body": (
            "Leonardo dissected human bodies at the Hospital of Santa Maria Nuova in Florence and "
            "later, between 1510 and 1511, collaborated with the anatomist Marcantonio della Torre "
            "of the University of Pavia. The intended treatise was never published, but the working "
            "material survives: more than 240 drawings accompanied by some 13,000 words of notes.\n\n"
            "He drew the skull, the muscles and tendons of the arm, the spine, and a foetus in the "
            "womb, and he was the first to describe the arterial thickening now called "
            "atherosclerosis. To study how blood moves through the aortic valve he cast a "
            "transparent glass model of the aorta and pumped a suspension of grass seed through it "
            "so he could watch the vortices form -- an experiment confirmed as correct only in the "
            "twentieth century."
        ),
    },
    {
        "book_id": "bk-amboise",
        "title": "Amboise, 1519: The Last Years in France",
        "author": "Curator's note",
        "summary": "Rome, the invitation from Francis I, and Clos Lucé.",
        "content_body": (
            "From 1513 to 1516 Leonardo lived in Rome, in the Belvedere Courtyard, under the "
            "patronage of Giuliano de' Medici, brother of Pope Leo X. The commissions he wanted did "
            "not come; Michelangelo and Raphael had the great papal projects.\n\n"
            "In 1516 Francis I of France invited him to court with a pension of 10,000 scudi and the "
            "manor house of Clos Lucé, next to the royal Château d'Amboise. Leonardo brought the "
            "'Mona Lisa' with him. By about the age of sixty-five his right hand was paralytic, "
            "probably from a stroke, and although he could still draw and teach with his left hand, "
            "he painted no more.\n\n"
            "He died at Clos Lucé on 2 May 1519, aged sixty-seven. His pupil and heir Francesco Melzi "
            "inherited the notebooks and paintings and carried them back to Italy. Leonardo was "
            "interred on 12 August 1519 in the Collegiate Church of Saint Florentin at Amboise."
        ),
    },
]


_LEONARDO_KNOWLEDGE: list[dict[str, Any]] = [
    {
        "doc_id": "kb-life",
        "title": "Life dates and places",
        "doc_type": "text",
        "content": (
            "Born 15 April 1452 near Vinci, Tuscany, about 35 km from Florence; illegitimate son of "
            "the notary Ser Piero da Vinci and Caterina di Meo Lippi. Apprenticed to Andrea del "
            "Verrocchio in Florence from about age 14; master of the Guild of Saint Luke in 1472. "
            "First Milanese period 1482-1499 under Ludovico Sforza. Venice 1500. Military engineer "
            "to Cesare Borgia in 1502, for whom he made the map of Imola. Rome 1513-1516 under "
            "Giuliano de' Medici. From 1516 in France at Clos Lucé beside the Château d'Amboise, at "
            "the invitation of Francis I, on a pension of 10,000 scudi. Died 2 May 1519, aged 67, "
            "probably of a stroke; his heir and executor was Francesco Melzi. Interred 12 August "
            "1519 in the Collegiate Church of Saint Florentin, Amboise."
        ),
    },
    {
        "doc_id": "kb-paintings",
        "title": "Principal paintings",
        "doc_type": "text",
        "content": (
            "The Baptism of Christ (c. 1472-75, with Verrocchio; Leonardo painted the angel; Uffizi). "
            "Landscape of the Arno Valley, pen and ink, dated 1473 -- his earliest dated work. "
            "Virgin of the Rocks. Lady with an Ermine (Cecilia Gallerani). The Last Supper "
            "(c. 1495-98, Santa Maria delle Grazie, Milan). Sala delle Asse (1498). Vitruvian Man "
            "(c. 1490). Mona Lisa / La Gioconda, begun October 1503, sitter Lisa del Giocondo, "
            "painted in sfumato -- glazes blended 'in the manner of smoke', without lines or borders. "
            "The Battle of Anghiari, lost, known through copies including one by Rubens; Michelangelo "
            "was assigned the opposite wall."
        ),
    },
    {
        "doc_id": "kb-notebooks",
        "title": "Notebooks and inventions",
        "doc_type": "text",
        "content": (
            "About 13,000 surviving pages, written left-handed in mirror-image cursive. Codices "
            "include the Codex Atlanticus, the Codex Arundel and the Codex on the Flight of Birds "
            "(c. 1505). Designs: ornithopter flying machine (c. 1488), aerial screw (c. 1489), "
            "parachute, giant crossbow, armoured fighting vehicle, self-propelled cart, mechanical "
            "knight and mechanical lion, double-hulled ship. Stated the laws of sliding friction in "
            "1493, rediscovered by Amontons in 1699; named first of the 23 'Men of Tribology'. Wrote "
            "'Il sole non si muove' -- the Sun does not move. Studied mathematics with Luca Pacioli "
            "and drew the solids for Pacioli's Divina proportione (1509)."
        ),
    },
    {
        "doc_id": "kb-anatomy",
        "title": "Anatomical work",
        "doc_type": "text",
        "content": (
            "Dissected at the Hospital of Santa Maria Nuova in Florence; collaborated 1510-11 with "
            "Marcantonio della Torre of the University of Pavia on an intended anatomical treatise "
            "that was never published. More than 240 drawings and some 13,000 words of notes survive. "
            "First to describe the arterial thickening now known as atherosclerosis. Built a "
            "transparent glass model of the aorta to observe vortices in the flow through the aortic "
            "valve -- an insight only confirmed in the twentieth century."
        ),
    },
    {
        "doc_id": "kb-sources",
        "title": "Source: Wikipedia, Leonardo da Vinci",
        "doc_type": "link",
        "url": "https://en.wikipedia.org/wiki/Leonardo_da_Vinci",
    },
    {
        "doc_id": "kb-vasari",
        "title": "Early biography",
        "doc_type": "text",
        "content": (
            "The main early account of Leonardo's life is Giorgio Vasari's 'Lives of the Most "
            "Excellent Painters, Sculptors and Architects' (1568). Vasari is the source of many "
            "famous anecdotes -- including Verrocchio abandoning painting after seeing Leonardo's "
            "angel -- but the Lives mixes documented fact with story, and some of it is apocryphal."
        ),
    },
]


_LEONARDO_STORY_NODES: list[dict[str, Any]] = [
    {
        "node_id": "intro",
        "character_line": (
            "Welcome to my bottega. Mind the plaster dust. I am Leonardo, of Vinci -- painter, "
            "yes, but I would rather you asked me about water, or birds, or the way a shoulder "
            "moves. What shall we look at first?"
        ),
        "choices": [
            {"text": "Tell me about your paintings.", "nextNodeId": "painting"},
            {"text": "How do you plan to make a man fly?", "nextNodeId": "flight"},
            {"text": "Why do you write backwards?", "nextNodeId": "mirror"},
            {"text": "What happened at the end of your life?", "nextNodeId": "amboise"},
        ],
    },
    {
        "node_id": "painting",
        "character_line": (
            "They ask always about the Florentine lady, begun in October of 1503. I never gave her "
            "up; she travels with me still. The trick is sfumato -- smoke. No line anywhere, only "
            "glaze upon glaze, so the eye can never find the edge and must invent it. In Milan I "
            "painted the Last Supper on a refectory wall, and I painted it too slowly, in a medium "
            "that would not hold. That was my error, not the wall's."
        ),
        "choices": [
            {"text": "And the angel that outshone your master?", "nextNodeId": "verrocchio"},
            {"text": "Show me something else.", "nextNodeId": "intro"},
        ],
    },
    {
        "node_id": "verrocchio",
        "character_line": (
            "In Verrocchio's shop I painted the kneeling angel in his Baptism of Christ, around "
            "1472. Vasari will one day write that my master laid down his brush forever in despair. "
            "It makes a fine story. In truth a bottega is a business: we cast bronze, gilded armour, "
            "built pageant machines. I learned more there in seven years than any university could "
            "have taught a notary's illegitimate son."
        ),
        "choices": [{"text": "Let us speak of other things.", "nextNodeId": "intro"}],
    },
    {
        "node_id": "flight",
        "character_line": (
            "A bird is an instrument working according to mathematical law, and it is within man's "
            "power to reproduce it. I have drawn the ornithopter, with wings a man beats by winch "
            "and pedal, and the aerial screw, which compresses the air and should rise into it as a "
            "screw rises into wood. I have drawn also a tent of linen by which a man may throw "
            "himself from any height without injury. I have not yet dared to try it."
        ),
        "choices": [
            {"text": "Did any of it work?", "nextNodeId": "friction"},
            {"text": "Let us speak of other things.", "nextNodeId": "intro"},
        ],
    },
    {
        "node_id": "friction",
        "character_line": (
            "Not the flying, no -- not yet. But not everything in those pages is a dream. In 1493 I "
            "set down the laws by which one surface slides upon another, and I am told no one will "
            "state them again for two hundred years. And I have poured grass seed through a glass "
            "heart to watch the blood turn in a vortex behind the valve. That is not a dream. That "
            "is simply looking, which almost nobody does."
        ),
        "choices": [{"text": "Let us speak of other things.", "nextNodeId": "intro"}],
    },
    {
        "node_id": "mirror",
        "character_line": (
            "Because my left hand runs from right to left and does not smear the ink -- that is the "
            "whole of the mystery, though it pleases people to imagine a code. There are some "
            "thirteen thousand pages of it now. Hold any one of them to a glass and it reads plainly "
            "enough. You will find shopping lists next to the anatomy, and a note that the Sun does "
            "not move, which I have chosen not to elaborate upon in public."
        ),
        "choices": [{"text": "Let us speak of other things.", "nextNodeId": "intro"}],
    },
    {
        "node_id": "amboise",
        "character_line": (
            "In 1516 the King of France invited me to Clos Lucé, beside his château at Amboise, and "
            "gave me a pension and, better, quiet. My right hand no longer obeys me; I draw and "
            "teach with the left. Melzi will keep the notebooks -- he is the only one I trust with "
            "them. I shall die here in May of 1519, at sixty-seven. Go and read the codices in the "
            "library, and watch the screens above. That is all any of it was ever for."
        ),
        "completion_flag": True,
    },
]


# ───────────────────────────── Escape room ──────────────────────────────


def _seed_alchemist_vault(registry: RoomsRegistry) -> None:
    _create_seed_room(
        registry, ESCAPE_ROOM_ID,
        name="The Alchemist's Vault",
        topic_tags=["escape-room", "puzzle", "history"],
        room_style="candlelit-vault",
        max_users=12,
    )
    builder = registry.get_builder(ESCAPE_ROOM_ID)
    assert builder is not None
    host = {"requester_id": SEED_HOST_ID, "is_room_host": True}

    registry.add_neighbor_tile(ESCAPE_ROOM_ID, (0, 0), "right")
    builder.configure_tile((0, 0), label="The Sealed Study", purpose_tag="puzzle")
    builder.configure_tile((1, 0), label="The Inner Vault", purpose_tag="puzzle")

    builder.configure_escape_session(
        enabled=True,
        time_limit_ms=ESCAPE_TIME_LIMIT_MS,
        briefing=(
            "The old master locked this study on the night he left for France and never came back. "
            "Four locks stand between you and the door, and every one of them is keyed to something "
            "he actually wrote or made. You have twenty minutes. Search the room, read everything, "
            "and if you get stuck, ask the apprentice -- he was here."
        ),
        team_mode=True,
        **host,
    )

    _seed_vault_scenery(builder)
    _seed_vault_puzzles(builder)
    _seed_vault_apprentice(builder)


def _seed_vault_scenery(builder: Any) -> None:
    host = {"requester_id": SEED_HOST_ID, "is_room_host": True}
    builder.create_object(
        "av-desk", "table", (0, 0), 250.0, 300.0, size_preset="L",
        color="dark-wood", material="wood", created_by=SEED_HOST_ID,
    )
    builder.create_object(
        "av-chair", "chair", (0, 0), 250.0, 400.0, size_preset="S",
        color="dark-wood", material="wood", created_by=SEED_HOST_ID,
    )
    builder.create_object(
        "av-shelf", "bookshelf", (0, 0), 640.0, 180.0, size_preset="L",
        color="dark-wood", material="wood", created_by=SEED_HOST_ID,
    )
    builder.add_book(
        "av-shelf", "av-bk-ledger", "The Master's Ledger",
        (
            "A water-stained account book. Most of it is sums, but the flyleaf carries three lines "
            "in a cramped, backwards hand:\n\n"
            "  'Born under the sign of the ram, in the year the tower was finished.'\n"
            "  'The smoke has no edges. Name the smoke and the second lock opens.'\n"
            "  'What I set down in ninety-three, they will not find again for two hundred years.'\n\n"
            "The last page is torn out."
        ),
        author="Unknown hand",
        summary="Three riddling lines on the flyleaf. The rest is arithmetic.",
        est_read_minutes=2,
        **host,
    )
    builder.add_book(
        "av-shelf", "av-bk-inventory", "Inventory of the Workshop",
        (
            "A list of what the master left behind, in the order he valued it:\n\n"
            "  one panel, a Florentine lady, unfinished, not to be sold\n"
            "  the codices, all of them, to Melzi and no other\n"
            "  a horse of clay, ruined\n"
            "  a glass heart, whole\n"
            "  a tent of linen, folded, never used\n\n"
            "At the bottom, in a different ink: 'The manor by the river. The King's own house stands "
            "above it. That is where I am going, and that is where I shall stop.'"
        ),
        author="Unknown hand",
        summary="What the master packed, and a hint about where he went.",
        est_read_minutes=2,
        **host,
    )
    builder.create_object(
        "av-vault-table", "table", (1, 0), 400.0, 320.0, size_preset="M",
        color="black", material="stone", created_by=SEED_HOST_ID,
    )
    builder.create_object(
        "av-clue-board", "clue_board", (0, 0), 400.0, 120.0, size_preset="L",
        color="dark-wood", material="wood", created_by=SEED_HOST_ID,
        config={
            "note": (
                "Pinned notes, in mirror writing: 'The ram -- 15 April.' 'Fifty-two years after "
                "fourteen hundred.' 'Sfumato: sfumare, to evaporate, to go up in smoke.' "
                "'Amontons will get the credit. Let him.'"
            ),
        },
    )


def _seed_vault_puzzles(builder: Any) -> None:
    host = {"requester_id": SEED_HOST_ID, "is_room_host": True}

    # The door first: puzzles that unlock it must reference an existing object.
    builder.create_object(
        "av-door", "escape_door", (1, 0), 400.0, 110.0, size_preset="L",
        color="black", material="metal", created_by=SEED_HOST_ID,
    )

    # 1. Numeric -- the birth year, from the ledger and the pinned notes.
    builder.create_object(
        "av-dial", "combination_dial", (0, 0), 130.0, 210.0, size_preset="M",
        color="gold-accent", material="metal", created_by=SEED_HOST_ID,
        config={"puzzleId": "av-puz-year"},
    )
    builder.add_puzzle(
        "av-puz-year",
        "A brass dial with four rings. 'Born under the sign of the ram, fifty-two years after "
        "fourteen hundred.' In what year was the master born?",
        "1452",
        hints=[
            "The ledger says 'fifty-two years after fourteen hundred'.",
            "The sign of the ram is Aries -- he was born on 15 April.",
            "The year is 1452.",
        ],
        match_mode="numeric",
        unlock_door_id="av-door",
        prop_type="combination_dial",
        max_attempts=8,
        **host,
    )

    # 2. Exact word -- the painting technique.
    builder.create_object(
        "av-cipher", "cipher_box", (0, 0), 560.0, 420.0, size_preset="M",
        color="dark-wood", material="wood", created_by=SEED_HOST_ID,
        config={"puzzleId": "av-puz-smoke"},
    )
    builder.add_puzzle(
        "av-puz-smoke",
        "A lacquered box with letter tiles. Scratched inside the lid: 'Blended without lines or "
        "borders, in the manner of smoke.' Name the technique.",
        "sfumato",
        hints=[
            "It is an Italian word, and it means roughly 'smoked' or 'evaporated'.",
            "The clue board spells out the root: sfumare, to go up in smoke.",
            "The answer is sfumato.",
        ],
        match_mode="exact",
        unlock_door_id="av-door",
        prop_type="cipher_box",
        reveal_item_id="av-item-key",
        max_attempts=10,
        **host,
    )

    # 3. Numeric -- the friction note.
    builder.create_object(
        "av-lock", "digital_lock", (1, 0), 180.0, 300.0, size_preset="M",
        color="black", material="metal", created_by=SEED_HOST_ID,
        config={"puzzleId": "av-puz-friction"},
    )
    builder.add_puzzle(
        "av-puz-friction",
        "A keypad, four digits. 'What I set down in ninety-three, they will not find again for two "
        "hundred years.' He meant the laws of sliding friction. Enter the full year he wrote them down.",
        "1493",
        hints=[
            "'Ninety-three' is the short form of a year in his own century.",
            "He was in Milan, working for Ludovico Sforza, at the time.",
            "The year is 1493.",
        ],
        match_mode="numeric",
        unlock_door_id="av-door",
        prop_type="digital_lock",
        max_attempts=8,
        **host,
    )

    # 4. Contains -- where he went. Deliberately forgiving, since a place
    #    name can be written several ways.
    builder.create_object(
        "av-tablet", "riddle_tablet", (1, 0), 620.0, 300.0, size_preset="M",
        color="natural-wood", material="stone", created_by=SEED_HOST_ID,
        config={"puzzleId": "av-puz-place"},
    )
    builder.add_puzzle(
        "av-puz-place",
        "A slate tablet, chalked over many times. 'The manor by the river; the King's own house "
        "stands above it. That is where I am going, and that is where I shall stop.' Name the town.",
        "amboise",
        hints=[
            "The King is Francis I of France, who invited him in 1516.",
            "The manor is Clos Lucé; the château above it gives the town its name.",
            "The town is Amboise, in the Loire valley.",
        ],
        match_mode="contains",
        unlock_door_id="av-door",
        prop_type="riddle_tablet",
        **host,
    )

    # A hidden item revealed by solving the cipher box, plus one found by
    # searching -- so both discovery routes are on show.
    builder.create_object(
        "av-item-key", "hidden_item", (0, 0), 690.0, 470.0, size_preset="S",
        color="gold-accent", material="metal", created_by=SEED_HOST_ID,
    )
    builder.configure_item("av-item-key", item_kind="key", single_use=True, **host)
    builder.create_object(
        "av-item-candle", "hidden_item", (1, 0), 300.0, 470.0, size_preset="S",
        color="white", material="wood", created_by=SEED_HOST_ID,
    )
    builder.configure_item("av-item-candle", item_kind="tool", single_use=False, **host)

    builder.configure_door("av-door", required_item_id="av-item-key", **host)


def _seed_vault_apprentice(builder: Any) -> None:
    host = {"requester_id": SEED_HOST_ID, "is_room_host": True}
    builder.create_object(
        "av-apprentice", "ai_character", (0, 0), 400.0, 430.0,
        color="navy", material="fabric", created_by=SEED_HOST_ID,
    )
    builder.configure_character(
        "av-apprentice", "Salaì, the Apprentice", "guide", "start", **host,
    )
    builder.configure_character_appearance(
        "av-apprentice",
        {
            "skinColor": "#E0AC69",
            "gender": "neutral",
            "hair": "curly",
            "beard": "none",
            "glasses": "none",
            "clothes": "tshirt",
            "accessory": "none",
        },
        **host,
    )
    builder.set_character_knowledge_base_title("av-apprentice", "What the apprentice remembers", **host)
    builder.add_character_knowledge_document(
        "av-apprentice", "av-kb-locks", "The four locks", "text",
        content=(
            "Four locks hold the vault door, and each is keyed to something the master wrote or "
            "made. The brass dial wants the year he was born, 1452. The lacquered cipher box wants "
            "the name of his painting technique, sfumato. The keypad in the inner vault wants 1493, "
            "the year he set down the laws of sliding friction. The slate tablet wants Amboise, the "
            "town he left for in 1516 at the invitation of Francis I, where he lived at Clos Lucé "
            "and died on 2 May 1519. Solving the cipher box also shakes a small brass key loose "
            "behind the shelf; the door will not open without it."
        ),
        **host,
    )
    for node in (
        {
            "node_id": "start",
            "character_line": (
                "Oh -- you got in. I've been stuck in here since he left for France. Four locks on "
                "that door, and every one of them is some private joke of his. I know what they're "
                "about, roughly. I just never paid attention when he explained things."
            ),
            "choices": [
                {"text": "Which lock should I start with?", "nextNodeId": "order"},
                {"text": "What do you actually remember about him?", "nextNodeId": "master"},
                {"text": "I'll search on my own.", "nextNodeId": "alone"},
            ],
        },
        {
            "node_id": "order",
            "character_line": (
                "The brass dial by the desk is the kindest -- it only wants a year, and the ledger "
                "on the shelf spells it out if you read the flyleaf. After that, the box with the "
                "letter tiles: something about smoke. The keypad and the slate are through the "
                "archway, in the inner vault. And read the pinned notes -- they're backwards, but "
                "they're not a code, he just wrote with his left hand."
            ),
            "choices": [{"text": "Anything else?", "nextNodeId": "start"}],
        },
        {
            "node_id": "master",
            "character_line": (
                "That he was never once satisfied. Thirteen thousand pages and hardly a finished "
                "painting among them. He kept the Florentine lady's portrait in his own room and "
                "wouldn't sell it. He left me nothing, incidentally -- the notebooks all went to "
                "Melzi. I'm told that was the correct decision."
            ),
            "choices": [{"text": "Back to the locks.", "nextNodeId": "start"}],
        },
        {
            "node_id": "alone",
            "character_line": (
                "Suit yourself. Read the ledger and the inventory on the shelf, and look at the "
                "pinned notes on the board. Everything you need is written down somewhere in here. "
                "Come and find me when you change your mind -- I'm not going anywhere."
            ),
            "completion_flag": True,
        },
    ):
        builder.add_story_node(
            "av-apprentice", node["node_id"], node["character_line"],
            choices=node.get("choices"), completion_flag=node.get("completion_flag", False),
            **host,
        )
