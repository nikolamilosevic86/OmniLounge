"""Generates the refined "Lounge" logo variants in client/public/img/branding/.

Four shape treatments of the same sofa mark, plus three palette options, so a
direction can be picked by comparing like with like. Run:

    .venv/bin/python scripts/make_logo_variants.py
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "client" / "public" / "img" / "branding"

BG = "#16111c"
WORDMARK = "#eae0e8"
SUBTITLE = "#b9a9c9"
TAGLINE = "BUILD  ·  LEARN  ·  ESCAPE"

# The original mark ran pink straight to cyan, which desaturates to grey through
# the middle. Every palette below either stays analogous or routes through
# violet so the blend stays clean.
PALETTES = {
    "blossom": ["#FFAEDC", "#B98CF2"],
    "aurora": ["#FFB0DE", "#C48BF0", "#7FD4EC"],
    "vivid": ["#FF7EC7", "#9B5DE5"],
}
SPARKLE = "#FFE3F6"


def gradient(gid: str, stops: list[str], diagonal: bool = True) -> str:
    x2, y2 = ("1", "1") if diagonal else ("0", "1")
    parts = "".join(
        f'<stop offset="{i / (len(stops) - 1):.2f}" stop-color="{c}"/>'
        for i, c in enumerate(stops)
    )
    return f'<linearGradient id="{gid}" x1="0" y1="0" x2="{x2}" y2="{y2}">{parts}</linearGradient>'


def sparkle(cx: float, cy: float, r: float, fill: str) -> str:
    """Four-point star, the accent already used across the app's UI."""
    s = r * 0.3
    return (
        f'<path d="M{cx} {cy - r} Q{cx + s} {cy - s} {cx + r} {cy} '
        f'Q{cx + s} {cy + s} {cx} {cy + r} Q{cx - s} {cy + s} {cx - r} {cy} '
        f'Q{cx - s} {cy - s} {cx} {cy - r} Z" fill="{fill}"/>'
    )


def mark_solid(g: str) -> str:
    """A: two shapes only -- a back cushion behind a full-width body. The back is
    slightly translucent so depth reads on light and dark surfaces alike,
    rather than being faked with a background-coloured band."""
    return f"""
    <rect x="11" y="15" width="50" height="23" rx="11.5" fill="url(#{g})" opacity="0.72"/>
    <rect x="5" y="31" width="62" height="25" rx="12" fill="url(#{g})"/>
    {sparkle(62, 12, 7, SPARKLE)}"""


def mark_line(g: str) -> str:
    """B: monoline. The most minimal of the four."""
    return f"""
    <g fill="none" stroke="url(#{g})" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M15 36 V26 a10 10 0 0 1 10 -10 h22 a10 10 0 0 1 10 10 v10"/>
      <rect x="8" y="35" width="56" height="20" rx="10"/>
      <path d="M17 55 v5"/>
      <path d="M55 55 v5"/>
    </g>
    {sparkle(62, 11, 6.5, SPARKLE)}"""


def mark_negative(g: str) -> str:
    """C: the same two-shape sofa knocked out of a solid gradient tile. The
    cushions are kept a few units apart so the gradient shows between them and
    the knockout doesn't merge into one blob."""
    return f"""
    <rect x="2" y="2" width="68" height="68" rx="18" fill="url(#{g})"/>
    <g fill="{BG}">
      <rect x="23" y="18" width="26" height="12" rx="6"/>
      <rect x="14" y="33" width="44" height="21" rx="9"/>
    </g>"""


def mark_arch(g: str) -> str:
    """D: reduced to two shapes -- an arch for the back, a bar for the seat."""
    return f"""
    <path d="M13 45 V34 a23 13 0 0 1 46 0 V45 Z" fill="url(#{g})" opacity="0.72"/>
    <rect x="6" y="42" width="60" height="16" rx="8" fill="url(#{g})"/>
    {sparkle(62, 13, 7, SPARKLE)}"""


MARKS = {
    "solid": mark_solid,
    "line": mark_line,
    "negative": mark_negative,
    "arch": mark_arch,
}


def write_icon(name: str, mark: str, gid: str, stops: list[str], tile: bool) -> None:
    tile_rect = f'<rect width="72" height="72" rx="16" fill="{BG}"/>' if tile else ""
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 72 72" width="72" height="72" role="img" aria-label="OmniLaunge icon">
  <defs>{gradient(gid, stops)}</defs>
  {tile_rect}{mark}
</svg>
"""
    (OUT / f"{name}.svg").write_text(svg)


def write_lockup(name: str, mark: str, gid: str, stops: list[str]) -> None:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 380 100" width="380" height="100" role="img" aria-label="OmniLaunge">
  <defs>{gradient(gid, stops)}</defs>
  <g transform="translate(4,14)">{mark}
  </g>
  <text x="92" y="47" font-family="'Roboto','Segoe UI',sans-serif" font-size="31" font-weight="700" letter-spacing="0.5" fill="{WORDMARK}">OmniLaunge</text>
  <text x="93" y="69" font-family="'Roboto','Segoe UI',sans-serif" font-size="11.5" font-weight="500" letter-spacing="2.4" fill="{SUBTITLE}">{TAGLINE}</text>
</svg>
"""
    (OUT / f"{name}.svg").write_text(svg)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    stops = PALETTES["aurora"]

    for shape, fn in MARKS.items():
        gid = f"g-{shape}"
        # The negative-space variant paints its own tile.
        write_icon(f"v2-icon-{shape}", fn(gid), gid, stops, tile=(shape != "negative"))
        write_lockup(f"v2-logo-{shape}", fn(gid), gid, stops)

    for pal, pstops in PALETTES.items():
        gid = f"g-solid-{pal}"
        write_icon(f"v2-palette-{pal}", mark_solid(gid), gid, pstops, tile=True)

    print(f"wrote {len(list(OUT.glob('v2-*.svg')))} files to {OUT}")


if __name__ == "__main__":
    main()
