"""Regenerates the Player Guide screenshots in client/img/guide/.

Run against a live server (default http://localhost:8000):

    .venv/bin/python scripts/capture_guide_screenshots.py

Screenshots are element-scoped and taken at a fixed 1440px-wide viewport so
the reader/playlist modals render in their two-pane desktop layout rather
than the narrow stacked one. Images are saved at deviceScaleFactor=2 and then
downscaled to a fixed display width, which keeps them crisp on HiDPI screens
without shipping needlessly huge files.
"""

import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OUT_DIR = Path(__file__).resolve().parent.parent / "client" / "public" / "img" / "guide"

VIEWPORT = {"width": 1440, "height": 1600}
SCALE = 2
# Final on-disk width. The guide never displays an image wider than ~880 CSS
# px, so 1200 keeps it sharp on retina without bloating the bundle.
DISPLAY_WIDTH = 1200

ROOM_FRAME = ".room-frame"


def shot(page, selector: str, name: str, max_height: int | None = None) -> None:
    locator = page.locator(selector)
    if max_height is not None:
        box = locator.bounding_box()
        if box and box["height"] > max_height:
            page.screenshot(
                path=str(OUT_DIR / f"{name}.png"),
                clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": max_height},
            )
            print(f"  captured {name} (clipped)")
            return
    locator.screenshot(path=str(OUT_DIR / f"{name}.png"))
    print(f"  captured {name}")


def downscale_all() -> None:
    for path in sorted(OUT_DIR.glob("*.png")):
        im = Image.open(path)
        if im.width > DISPLAY_WIDTH:
            ratio = DISPLAY_WIDTH / im.width
            im = im.resize((DISPLAY_WIDTH, round(im.height * ratio)), Image.LANCZOS)
            im.save(path, optimize=True)
        print(f"  {path.name}: {im.size[0]}x{im.size[1]}")


def radial_action(page, label: str) -> None:
    """Clicks a radial-menu item by aria-label. The canvas overlaps the menu
    for hit-testing purposes, so a plain Playwright click is intercepted."""
    page.evaluate(
        """(label) => {
            const btn = Array.from(document.querySelectorAll('.radial-item'))
              .find((b) => b.getAttribute('aria-label') === label);
            btn?.click();
        }""",
        label,
    )


def open_object_menu(page, fx: float, fy: float, expect: str) -> bool:
    """Clicks the room canvas at a fractional position and reports whether the
    expected object's radial menu opened."""
    box = page.locator("#room-canvas").bounding_box()
    page.mouse.click(box["x"] + fx * box["width"], box["y"] + fy * box["height"])
    page.wait_for_timeout(450)
    text = page.evaluate("() => document.querySelector('.radial-menu')?.innerText ?? ''")
    if expect.lower() in text.lower():
        return True
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    return False


def find_object(page, spots, expect: str) -> bool:
    for fx, fy in spots:
        if open_object_menu(page, fx, fy, expect):
            return True
    return False


def join_room(page, room_id: str) -> None:
    page.evaluate("() => document.getElementById('change-room-btn')?.click()")
    page.wait_for_timeout(700)
    page.evaluate(f"() => document.querySelector('[data-room-id=\"{room_id}\"]')?.click()")
    page.wait_for_timeout(1600)


def current_tile(page) -> str:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('*'))
             .filter((el) => el.children.length === 0 && /Tile \\(/.test(el.textContent || ''))
             .map((el) => el.textContent.trim())[0] || ''"""
    )


def walk_to_right_tile(page, target: str) -> None:
    """Click-to-move toward the right doorway until the tile indicator flips.
    Arrow keys are unreliable here because a canvas click cancels the held
    keyboard direction."""
    canvas = page.locator("#room-canvas")
    for _ in range(12):
        if current_tile(page) == target:
            return
        canvas.click(position={"x": 792, "y": 540})
        page.wait_for_timeout(850)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_context(viewport=VIEWPORT, device_scale_factor=SCALE).new_page()

        print("Avatar creator + room chooser...")
        page.goto(BASE_URL)
        page.wait_for_timeout(1200)
        shot(page, "#creator-screen .creator-container", "avatar-creator")

        page.locator("#username-input").fill("Guide Author")
        page.evaluate("() => document.getElementById('enter-room-btn').click()")
        page.wait_for_timeout(1800)
        shot(page, ".room-chooser-card", "room-chooser")

        print("Lobby + build mode...")
        page.evaluate("() => document.getElementById('room-chooser-close')?.click()")
        page.wait_for_timeout(800)
        shot(page, ROOM_FRAME, "lobby-room")

        page.evaluate("() => document.getElementById('build-mode-toggle')?.click()")
        page.wait_for_timeout(1000)
        # The real panel is a narrow 2-column ribbon, which makes a 500x2000
        # figure that clips half the catalog. Widen it just for the capture so
        # all 15 object types are legible in one image.
        page.add_style_tag(content="""
            #build-controls { width: 900px !important; max-width: 900px !important; }
            #build-controls .catalog-grid { grid-template-columns: repeat(5, 1fr) !important; }
        """)
        page.wait_for_timeout(600)
        shot(page, "#build-controls .builder-section:has(#catalog-grid)", "build-mode-catalog")
        page.evaluate("() => document.getElementById('build-mode-toggle')?.click()")
        page.wait_for_timeout(500)

        print("Leonardo's Workshop...")
        join_room(page, "leonardo-workshop")
        shot(page, ROOM_FRAME, "leonardo-workshop-bottega")

        # Leonardo stands on the right of the bottega tile.
        if find_object(page, [(0.80, 0.70), (0.78, 0.66), (0.82, 0.74)], "ai_character"):
            shot(page, ROOM_FRAME, "radial-menu")
            radial_action(page, "Talk")
            page.wait_for_timeout(1200)
            page.evaluate("() => document.querySelectorAll('#dialogue-choice-list button')[0]?.click()")
            page.wait_for_timeout(1000)
            shot(page, "#dialogue-modal .reader-modal-card", "ai-character-dialogue")
            page.evaluate("() => document.getElementById('dialogue-modal-close')?.click()")
            page.wait_for_timeout(500)

        walk_to_right_tile(page, "Tile (1, 0)")
        page.wait_for_timeout(700)
        shot(page, ROOM_FRAME, "leonardo-workshop-library")

        if find_object(page, [(0.50, 0.36), (0.50, 0.33), (0.50, 0.30)], "bookshelf"):
            radial_action(page, "Browse Books")
            page.wait_for_timeout(1400)
            shot(page, "#reader-modal .reader-modal-card", "bookshelf-reader")
            page.evaluate("() => document.getElementById('reader-modal-close')?.click()")
            page.wait_for_timeout(500)

        print("The Alchemist's Vault...")
        join_room(page, "alchemist-vault")
        shot(page, ROOM_FRAME, "vault-sealed-study")

        if find_object(page, [(0.16, 0.35), (0.21, 0.41), (0.16, 0.30)], "combination_dial"):
            shot(page, ROOM_FRAME, "vault-puzzle-radial")
            radial_action(page, "Solve")
            page.wait_for_timeout(900)
            shot(page, "#puzzle-modal .reader-modal-card", "vault-puzzle-modal")

        browser.close()

    print("Downscaling...")
    downscale_all()


if __name__ == "__main__":
    main()
