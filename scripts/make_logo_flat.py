"""Generates the flat (gradient-free) monoline lounge mark.

Shape B from the earlier round, drawn with a single solid stroke instead of a
gradient, in several colourways. Run:

    .venv/bin/python scripts/make_logo_flat.py
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "client" / "public" / "img" / "branding"

BG = "#16111c"
TAGLINE = "BUILD  ·  LEARN  ·  ESCAPE"

# Flat colourways. "adaptive" paints with currentColor so the mark simply
# inherits the surrounding text colour and follows the app's light/dark theme
# without shipping two files.
COLOURWAYS = {
    "adaptive": {"stroke": "currentColor", "accent": "currentColor", "text": "currentColor"},
    "pink": {"stroke": "#F4ADDB", "accent": "#F4ADDB", "text": "#eae0e8"},
    "violet": {"stroke": "#C48BF0", "accent": "#C48BF0", "text": "#eae0e8"},
    "cyan": {"stroke": "#7FD4EC", "accent": "#7FD4EC", "text": "#eae0e8"},
    "ivory": {"stroke": "#EAE0E8", "accent": "#EAE0E8", "text": "#eae0e8"},
    "plum": {"stroke": "#8B4B82", "accent": "#8B4B82", "text": "#2a1027"},
    # Two-tone: still flat, just two solid colours instead of a blend.
    "duo": {"stroke": "#F4ADDB", "accent": "#7FD4EC", "text": "#eae0e8"},
}


def sparkle(cx: float, cy: float, r: float, fill: str) -> str:
    """Four-point star, the accent already used across the app's UI."""
    s = r * 0.3
    return (
        f'<path d="M{cx} {cy - r} Q{cx + s} {cy - s} {cx + r} {cy} '
        f'Q{cx + s} {cy + s} {cx} {cy + r} Q{cx - s} {cy + s} {cx - r} {cy} '
        f'Q{cx - s} {cy - s} {cx} {cy - r} Z" fill="{fill}"/>'
    )


def mark(stroke: str, accent: str) -> str:
    return f"""
    <g fill="none" stroke="{stroke}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M15 36 V26 a10 10 0 0 1 10 -10 h22 a10 10 0 0 1 10 10 v10"/>
      <rect x="8" y="35" width="56" height="20" rx="10"/>
      <path d="M17 55 v5"/>
      <path d="M55 55 v5"/>
    </g>
    {sparkle(62, 11, 6.5, accent)}"""


def write_icon(name: str, stroke: str, accent: str, tile: str | None) -> None:
    tile_rect = f'<rect width="72" height="72" rx="16" fill="{tile}"/>' if tile else ""
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 72 72" width="72" height="72" role="img" aria-label="OmniLaunge icon">
  {tile_rect}{mark(stroke, accent)}
</svg>
"""
    (OUT / f"{name}.svg").write_text(svg)


def write_lockup(name: str, stroke: str, accent: str, text: str) -> None:
    subtitle_opacity = "0.7" if text == "currentColor" else "1"
    subtitle_fill = text if text == "currentColor" else "#b9a9c9"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 380 100" width="380" height="100" role="img" aria-label="OmniLaunge">
  <g transform="translate(4,14)">{mark(stroke, accent)}
  </g>
  <text x="92" y="47" font-family="'Roboto','Segoe UI',sans-serif" font-size="31" font-weight="700" letter-spacing="0.5" fill="{text}">OmniLaunge</text>
  <text x="93" y="69" font-family="'Roboto','Segoe UI',sans-serif" font-size="11.5" font-weight="500" letter-spacing="2.4" fill="{subtitle_fill}" opacity="{subtitle_opacity}">{TAGLINE}</text>
</svg>
"""
    (OUT / f"{name}.svg").write_text(svg)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, c in COLOURWAYS.items():
        # The adaptive mark must stay transparent so it can sit on any surface.
        tile = None if name in ("adaptive", "plum") else BG
        write_icon(f"v3-icon-{name}", c["stroke"], c["accent"], tile)
        write_lockup(f"v3-logo-{name}", c["stroke"], c["accent"], c["text"])

    # The two assets the app actually ships. The mark is adaptive so it takes
    # its colour from whatever it is inlined into; the favicon cannot rely on
    # currentColor (browser chrome gives it no inherited colour), so it carries
    # its own tile and a fixed brand stroke.
    canonical = OUT.parent
    (canonical / "logo-mark.svg").write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 72 72" role="img" aria-label="OmniLaunge">
  {mark("currentColor", "currentColor")}
</svg>
"""
    )
    (canonical.parent / "favicon.svg").write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 72 72" role="img" aria-label="OmniLaunge">
  <rect width="72" height="72" rx="16" fill="{BG}"/>{mark("#F4ADDB", "#F4ADDB")}
</svg>
"""
    )

    print(f"wrote {len(list(OUT.glob('v3-*.svg')))} variants to {OUT}")
    print(f"wrote canonical logo-mark.svg and favicon.svg")


if __name__ == "__main__":
    main()
