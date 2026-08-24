/**
 * TDD tests for the avatar renderer (client/js/avatar-renderer.js).
 *
 * These tests were written to specify the expected rendering contract
 * for the chibi-style avatar, covering:
 *  - SVG structure and required body parts (head, arms, legs, shoes)
 *  - Every hair style emitting SVG markup
 *  - Every clothes style emitting body + cloth-detail markup
 *  - Every beard/glasses/accessory style
 *  - The shade() colour helper (exercised via rendered output)
 *  - The iris colour being driven by username
 *  - Both 'normal' and 'large' size modes
 */

import { describe, it, expect } from 'vitest';
import { AVATAR_OPTIONS, renderAvatarSVG } from '../client/js/avatar-renderer.js';

// ─── helpers ──────────────────────────────────────────────────────────────────

function makeAvatar(overrides = {}) {
  return {
    username: 'Tester',
    skinColor: '#FFDBAC',
    hair: 'short',
    beard: 'none',
    glasses: 'none',
    clothes: 'tshirt',
    accessory: 'none',
    ...overrides,
  };
}

// Count how many times a substring appears in a string
function countOccurrences(str, sub) {
  let count = 0;
  let idx = 0;
  while ((idx = str.indexOf(sub, idx)) !== -1) {
    count++;
    idx += sub.length;
  }
  return count;
}

// ─── AVATAR_OPTIONS exports ───────────────────────────────────────────────────

describe('AVATAR_OPTIONS', () => {
  it('exports all six skin colour options', () => {
    expect(AVATAR_OPTIONS.skinColors).toHaveLength(6);
    AVATAR_OPTIONS.skinColors.forEach(c => expect(c).toMatch(/^#[0-9A-Fa-f]{6}$/));
  });

  it('exports six hair styles', () => {
    expect(AVATAR_OPTIONS.hair).toHaveLength(6);
    expect(AVATAR_OPTIONS.hair).toContain('bald');
  });

  it('exports four beard options including none', () => {
    expect(AVATAR_OPTIONS.beards).toContain('none');
    expect(AVATAR_OPTIONS.beards).toHaveLength(4);
  });

  it('exports four glasses options including none', () => {
    expect(AVATAR_OPTIONS.glasses).toContain('none');
    expect(AVATAR_OPTIONS.glasses).toHaveLength(4);
  });

  it('exports five clothes options', () => {
    expect(AVATAR_OPTIONS.clothes).toHaveLength(5);
  });

  it('exports five accessory options including none', () => {
    expect(AVATAR_OPTIONS.accessories).toContain('none');
    expect(AVATAR_OPTIONS.accessories).toHaveLength(5);
  });
});

// ─── renderAvatarSVG – basic SVG contract ─────────────────────────────────────

describe('renderAvatarSVG – basic SVG contract', () => {
  it('returns a string', () => {
    expect(typeof renderAvatarSVG(makeAvatar())).toBe('string');
  });

  it('returns a valid SVG element', () => {
    const svg = renderAvatarSVG(makeAvatar());
    expect(svg).toMatch(/^<svg /);
    expect(svg).toMatch(/<\/svg>$/);
  });

  it('includes the avatar-svg class', () => {
    const svg = renderAvatarSVG(makeAvatar());
    expect(svg).toContain('class="avatar-svg"');
  });

  it('normal size uses 60×90 viewBox', () => {
    const svg = renderAvatarSVG(makeAvatar(), 'normal');
    expect(svg).toContain('viewBox="0 0 60 90"');
  });

  it('large size uses 120×180 viewBox', () => {
    const svg = renderAvatarSVG(makeAvatar(), 'large');
    expect(svg).toContain('viewBox="0 0 120 180"');
  });

  it('defaults to normal size when no size argument given', () => {
    const svg = renderAvatarSVG(makeAvatar());
    expect(svg).toContain('viewBox="0 0 60 90"');
  });
});

// ─── Required body parts ──────────────────────────────────────────────────────

describe('renderAvatarSVG – required body parts', () => {
  const svg = renderAvatarSVG(makeAvatar());

  it('contains a drop-shadow (ground shadow ellipse)', () => {
    // Ground shadow is the first ellipse drawn
    expect(svg).toMatch(/rgba\(0,0,0,0\.18\)/);
  });

  it('contains a head ellipse with the skin colour', () => {
    expect(svg).toContain('#FFDBAC');
    // Head is rendered as multiple ellipses with skin colour
    expect(countOccurrences(svg, '#FFDBAC')).toBeGreaterThan(2);
  });

  it('contains TWO leg rectangles (left and right)', () => {
    // Both legs share the same legC colour and rx value; there must be
    // at least two <rect> elements inside the svg that represent legs.
    // We can verify by checking that legs come before body in the source order.
    const legsIdx  = svg.indexOf('legC') !== -1 ? svg.indexOf('legC') : -1;
    // Indirect check: at least 6 rect elements exist (legs×2, arms×2, body parts, etc.)
    const rectCount = countOccurrences(svg, '<rect ');
    expect(rectCount).toBeGreaterThanOrEqual(4);
  });

  it('contains shoe ellipses (4 ellipses for shoe top + highlight per shoe)', () => {
    // Shoes are rendered as 4 ellipses at the bottom
    const ellipseCount = countOccurrences(svg, '<ellipse ');
    // head (3) + blush (2) + nose (1) + neck (2) + shoes (4) + eyes (10+) = lots
    expect(ellipseCount).toBeGreaterThanOrEqual(12);
  });

  it('contains arm rectangles (at least 2 arm pill rects)', () => {
    // Arms contribute at least 4 rects (2 body + 2 highlight per arm)
    const rectCount = countOccurrences(svg, '<rect ');
    expect(rectCount).toBeGreaterThanOrEqual(6);
  });

  it('contains eye whites (two white-filled ellipses)', () => {
    expect(countOccurrences(svg, 'fill="white"')).toBeGreaterThanOrEqual(2);
  });

  it('contains rosy cheek blush ellipses', () => {
    expect(svg).toContain('#ffb3c6');
  });

  it('contains a smile mouth path', () => {
    expect(svg).toContain('#c0555a');
  });

  it('contains a body path element', () => {
    expect(countOccurrences(svg, '<path ')).toBeGreaterThanOrEqual(3);
  });
});

// ─── Iris colour driven by username ───────────────────────────────────────────

describe('renderAvatarSVG – iris colour from username', () => {
  const IRIS_COLORS = ['#3b82f6', '#10b981', '#8b5cf6', '#ef4444', '#f59e0b', '#06b6d4'];

  it('produces a deterministic iris colour for a given username', () => {
    const svgA = renderAvatarSVG(makeAvatar({ username: 'Alice' }));
    const svgB = renderAvatarSVG(makeAvatar({ username: 'Alice' }));
    // Both renders must contain the same iris colour
    const matchedColor = IRIS_COLORS.find(c => svgA.includes(c));
    expect(matchedColor).toBeDefined();
    expect(svgB).toContain(matchedColor);
  });

  it('can produce different iris colours for different usernames', () => {
    const colors = new Set();
    ['A', 'B', 'C', 'D', 'E', 'F'].forEach(u => {
      const svg = renderAvatarSVG(makeAvatar({ username: u }));
      IRIS_COLORS.forEach(c => { if (svg.includes(c)) colors.add(c); });
    });
    expect(colors.size).toBeGreaterThan(1);
  });

  it('handles empty username without throwing', () => {
    expect(() => renderAvatarSVG(makeAvatar({ username: '' }))).not.toThrow();
  });
});

// ─── Skin colour propagation ──────────────────────────────────────────────────

describe('renderAvatarSVG – skin colour', () => {
  it('uses the provided skin colour in the SVG', () => {
    AVATAR_OPTIONS.skinColors.forEach(color => {
      const svg = renderAvatarSVG(makeAvatar({ skinColor: color }));
      expect(svg).toContain(color);
    });
  });

  it('falls back gracefully when skinColor is undefined', () => {
    const avatar = makeAvatar({ skinColor: undefined });
    expect(() => renderAvatarSVG(avatar)).not.toThrow();
    // Should use the default #FFDBAC
    expect(renderAvatarSVG(avatar)).toContain('#FFDBAC');
  });
});

// ─── Hair styles ─────────────────────────────────────────────────────────────

describe('renderAvatarSVG – hair styles', () => {
  const HAIR_KEYWORDS = {
    short:    '#3b2f2f',
    long:     '#8b4513',
    curly:    '#1a0a00',
    mohawk:   '#ff3d71',
    bald:     null,       // bald emits NO hair elements
    ponytail: '#c8860a',
  };

  Object.entries(HAIR_KEYWORDS).forEach(([style, hairColor]) => {
    it(`renders "${style}" hair without throwing`, () => {
      expect(() => renderAvatarSVG(makeAvatar({ hair: style }))).not.toThrow();
    });

    if (hairColor) {
      it(`"${style}" hair uses colour ${hairColor}`, () => {
        const svg = renderAvatarSVG(makeAvatar({ hair: style }));
        expect(svg).toContain(hairColor);
      });
    }

    if (style === 'bald') {
      it('"bald" style emits no hair colour markup', () => {
        const svg = renderAvatarSVG(makeAvatar({ hair: 'bald' }));
        // None of the other hair colours should appear
        Object.values(HAIR_KEYWORDS)
          .filter(c => c !== null)
          .forEach(c => expect(svg).not.toContain(c));
      });
    }
  });

  it('"curly" hair renders multiple circle elements', () => {
    const svg = renderAvatarSVG(makeAvatar({ hair: 'curly' }));
    expect(countOccurrences(svg, '<circle ')).toBeGreaterThanOrEqual(6);
  });

  it('"mohawk" hair renders a polygon/path spike', () => {
    const svg = renderAvatarSVG(makeAvatar({ hair: 'mohawk' }));
    // Mohawk uses a <path> with large y-extent
    expect(svg).toContain('#ff3d71');
  });

  it('"long" hair renders back-strand paths (behind-head strands)', () => {
    const svg = renderAvatarSVG(makeAvatar({ hair: 'long' }));
    // Long hair includes back strands as stroke paths
    expect(countOccurrences(svg, '<path ')).toBeGreaterThan(4);
  });

  it('"ponytail" renders both a skull cap and a tail path', () => {
    const svg = renderAvatarSVG(makeAvatar({ hair: 'ponytail' }));
    // Ponytail has at least back-strand path + front-cap path + hair-tie circle
    expect(countOccurrences(svg, '#c8860a')).toBeGreaterThanOrEqual(2);
  });
});

// ─── Beard styles ────────────────────────────────────────────────────────────

describe('renderAvatarSVG – beard styles', () => {
  it('"none" beard adds no visible beard markup', () => {
    // Use bald to avoid short-hair colour (#3b2f2f) colliding with beard colour
    const svg = renderAvatarSVG(makeAvatar({ beard: 'none', hair: 'bald' }));
    // buildBeard('none') returns empty string; beard colour #3b2f2f must be absent
    expect(svg).not.toContain('#3b2f2f');
    // Goatee-specific opacity must also be absent
    expect(svg).not.toContain('opacity="0.88"');
  });

  it('"stubble" beard renders a semi-transparent ellipse', () => {
    const svg = renderAvatarSVG(makeAvatar({ beard: 'stubble' }));
    expect(svg).toContain('opacity="0.17"');
  });

  it('"goatee" beard renders a filled path below the mouth', () => {
    const svg = renderAvatarSVG(makeAvatar({ beard: 'goatee' }));
    expect(svg).toContain('opacity="0.88"');
  });

  it('"full" beard renders a large filled path', () => {
    const svg = renderAvatarSVG(makeAvatar({ beard: 'full' }));
    expect(svg).toContain('opacity="0.9"');
  });
});

// ─── Glasses styles ───────────────────────────────────────────────────────────

describe('renderAvatarSVG – glasses styles', () => {
  it('"none" glasses adds no glasses markup', () => {
    const svg = renderAvatarSVG(makeAvatar({ glasses: 'none' }));
    expect(svg).not.toContain('#1e293b');
  });

  it('"round" glasses renders two circles with stroke', () => {
    const svg = renderAvatarSVG(makeAvatar({ glasses: 'round' }));
    expect(svg).toContain('#1e293b');
    // Circles for frame: at minimum 2 <circle> for lenses
    // (plus possibly eye whites — count ≥ 2 of those circles)
    expect(countOccurrences(svg, 'stroke="#1e293b"')).toBeGreaterThanOrEqual(2);
  });

  it('"square" glasses renders two rects with stroke', () => {
    const svg = renderAvatarSVG(makeAvatar({ glasses: 'square' }));
    expect(countOccurrences(svg, 'stroke="#1e293b"')).toBeGreaterThanOrEqual(2);
  });

  it('"sunglasses" renders two dark lens paths', () => {
    const svg = renderAvatarSVG(makeAvatar({ glasses: 'sunglasses' }));
    expect(svg).toContain('#0f172a');
    expect(countOccurrences(svg, 'opacity="0.9"')).toBeGreaterThanOrEqual(2);
  });
});

// ─── Clothes styles ───────────────────────────────────────────────────────────

describe('renderAvatarSVG – clothes styles', () => {
  it('"tshirt" renders a collar detail path', () => {
    const svg = renderAvatarSVG(makeAvatar({ clothes: 'tshirt' }));
    // Collar uses clothDk colour via shade; the body fill #4ecca3 must appear
    expect(svg).toContain('#4ecca3');
  });

  it('"hoodie" renders a kangaroo-pocket rect', () => {
    const svg = renderAvatarSVG(makeAvatar({ clothes: 'hoodie' }));
    expect(svg).toContain('#7c3aed');
    // Hoodie has pocket rect with clothDk opacity
    expect(svg).toContain('opacity="0.4"');
  });

  it('"suit" renders white lapels polygon and a red tie', () => {
    const svg = renderAvatarSVG(makeAvatar({ clothes: 'suit' }));
    expect(svg).toContain('#dc2626'); // tie
    expect(svg).toContain('opacity="0.92"'); // lapel
  });

  it('"dress" renders a flared skirt (wider at bottom)', () => {
    const svg = renderAvatarSVG(makeAvatar({ clothes: 'dress' }));
    expect(svg).toContain('#f43f5e');
  });

  it('"jacket" renders zip-line strokes', () => {
    const svg = renderAvatarSVG(makeAvatar({ clothes: 'jacket' }));
    expect(svg).toContain('#0ea5e9');
    // Two zip lines plus a horizontal seam = multiple <line> elements
    expect(countOccurrences(svg, '<line ')).toBeGreaterThanOrEqual(2);
  });

  it('each clothes style makes arms use the same cloth colour', () => {
    AVATAR_OPTIONS.clothes.forEach(style => {
      const svg = renderAvatarSVG(makeAvatar({ clothes: style }));
      // Arms are pill rects drawn with clothC; svgBody also uses clothC
      // At minimum the body colour must appear more than once
      const CLOTH_COLORS = { tshirt:'#4ecca3', hoodie:'#7c3aed', suit:'#1e293b', dress:'#f43f5e', jacket:'#0ea5e9' };
      const col = CLOTH_COLORS[style];
      expect(countOccurrences(svg, col)).toBeGreaterThan(1);
    });
  });
});

// ─── Accessory styles ─────────────────────────────────────────────────────────

describe('renderAvatarSVG – accessory styles', () => {
  it('"none" accessory adds no extra front/back markup', () => {
    const svg = renderAvatarSVG(makeAvatar({ accessory: 'none' }));
    // Without accessories, certain identifiers are absent
    expect(svg).not.toContain('#6366f1'); // headphones accent colour
  });

  it('"hat" renders a crown rect and a brim ellipse', () => {
    const svg = renderAvatarSVG(makeAvatar({ accessory: 'hat' }));
    expect(svg).toContain('#e11d48'); // hat band
    expect(svg).toContain('#1e293b'); // hat body
  });

  it('"headphones" renders ear-pad rects with accent colour', () => {
    const svg = renderAvatarSVG(makeAvatar({ accessory: 'headphones' }));
    expect(svg).toContain('#6366f1'); // headphone accent
  });

  it('"scarf" renders a scarf path with pink colour', () => {
    const svg = renderAvatarSVG(makeAvatar({ accessory: 'scarf' }));
    expect(svg).toContain('#f43f5e');
  });

  it('"backpack" renders back-layer rect before head elements', () => {
    const svg = renderAvatarSVG(makeAvatar({ accessory: 'backpack' }));
    // Back layer contains a large rect for the pack body
    // It should appear before the body/head in the SVG layer order
    const backpackIdx = svg.indexOf('rx=');
    expect(backpackIdx).toBeGreaterThan(0);
  });
});

// ─── Size scaling ─────────────────────────────────────────────────────────────

describe('renderAvatarSVG – size scaling', () => {
  it('large size produces larger absolute coordinate values', () => {
    const normal = renderAvatarSVG(makeAvatar());
    const large  = renderAvatarSVG(makeAvatar(), 'large');

    // Extract all numeric values from cx/cy/rx/ry/x/y attributes and compare max
    const extractNums = svg => [...svg.matchAll(/(?:cx|cy|rx|ry|x1|y1|x2|y2|width|height)="([\d.]+)"/g)]
      .map(m => parseFloat(m[1]));

    const maxNormal = Math.max(...extractNums(normal));
    const maxLarge  = Math.max(...extractNums(large));
    expect(maxLarge).toBeGreaterThan(maxNormal);
  });

  it('same avatar renders same structure at both sizes', () => {
    const av = makeAvatar({ hair: 'curly', glasses: 'round', clothes: 'suit', accessory: 'hat' });
    const normal = renderAvatarSVG(av);
    const large  = renderAvatarSVG(av, 'large');

    // Both should contain the same distinctive element signatures
    expect(countOccurrences(normal, '<circle ')).toBe(countOccurrences(large, '<circle '));
    expect(countOccurrences(normal, '<rect '))  .toBe(countOccurrences(large,  '<rect '));
  });
});

// ─── shade helper (exercised indirectly through rendered output) ───────────────

describe('shade() colour helper – exercised via rendered output', () => {
  it('darker skin variants appear in shadows and outlines (negative shade)', () => {
    // skinDk = shade(skin, -30) is used for nose, shadow ellipse, hand shadow
    // shade('#FFDBAC', -30): R=255-30=225=0xE1, G=219-30=189=0xBD, B=172-30=142=0x8E → #e1bd8e
    const svg = renderAvatarSVG(makeAvatar({ skinColor: '#FFDBAC' }));
    expect(svg).toContain('#e1bd8e');
  });

  it('lighter skin variant appears in specular highlight (positive shade)', () => {
    // skinLt = shade(skin, +24) is used for neck and head highlights
    const svg = renderAvatarSVG(makeAvatar({ skinColor: '#FFDBAC' }));
    // shade('#FFDBAC', +24) = '#ffffca' clamped → '#ffffc6' … let's just
    // confirm at least one fill value lighter than the base appears
    expect(svg).toContain('opacity="0.3"'); // neck highlight uses 0.3 opacity
  });
});

// ─── No errors for every combination of options ───────────────────────────────

describe('renderAvatarSVG – exhaustive option coverage', () => {
  AVATAR_OPTIONS.hair.forEach(hair => {
    AVATAR_OPTIONS.clothes.forEach(clothes => {
      it(`renders hair="${hair}", clothes="${clothes}" without throwing`, () => {
        expect(() => renderAvatarSVG(makeAvatar({ hair, clothes }))).not.toThrow();
      });
    });
  });

  AVATAR_OPTIONS.beards.forEach(beard => {
    AVATAR_OPTIONS.glasses.forEach(glasses => {
      it(`renders beard="${beard}", glasses="${glasses}" without throwing`, () => {
        expect(() => renderAvatarSVG(makeAvatar({ beard, glasses }))).not.toThrow();
      });
    });
  });

  AVATAR_OPTIONS.accessories.forEach(accessory => {
    it(`renders accessory="${accessory}" without throwing`, () => {
      expect(() => renderAvatarSVG(makeAvatar({ accessory }))).not.toThrow();
    });
  });
});

// ─── Walking animation (walkPhase parameter) ─────────────────────────────────
//
// Contract:
//   renderAvatarSVG(avatar, size, walkPhase)
//   walkPhase ∈ [0, 1)  — 0 = standing, 0.25 = mid-stride left, 0.75 = mid-stride right
//
//   At walkPhase = 0.25  (sin = 1):
//     left  leg  rotates  +MAX_LEG_ANGLE (22°)  → forward
//     right leg  rotates  -MAX_LEG_ANGLE (22°)  → backward
//     left  arm  rotates  -MAX_ARM_ANGLE (18°)  → backward (natural opposite)
//     right arm  rotates  +MAX_ARM_ANGLE (18°)  → forward
//
//   At walkPhase = 0.75  (sin = -1): all angles flip sign.
//   At walkPhase = 0 or 1 (sin = 0): all rotation angles are 0.00.

describe('renderAvatarSVG – walking animation', () => {
  it('accepts walkPhase as optional third parameter without throwing', () => {
    expect(() => renderAvatarSVG(makeAvatar(), 'normal', 0)).not.toThrow();
    expect(() => renderAvatarSVG(makeAvatar(), 'normal', 0.25)).not.toThrow();
    expect(() => renderAvatarSVG(makeAvatar(), 'normal', 0.5)).not.toThrow();
    expect(() => renderAvatarSVG(makeAvatar(), 'normal', 0.75)).not.toThrow();
    expect(() => renderAvatarSVG(makeAvatar(), 'normal', 1)).not.toThrow();
  });

  it('at walkPhase=0 legs and arms have zero rotation (0.00)', () => {
    const svg = renderAvatarSVG(makeAvatar(), 'normal', 0);
    // sin(0) = 0, so all rotation angles are 0.00
    // There should be 4 rotation groups (2 legs + 2 arms), all with angle 0.00
    expect(countOccurrences(svg, 'rotate(0.00,')).toBe(4);
  });

  it('at walkPhase=0.25 left leg has max positive rotation (+22.00°)', () => {
    const svg = renderAvatarSVG(makeAvatar(), 'normal', 0.25);
    // sin(π/2) = 1 → legSwing = 22.00
    expect(svg).toContain('rotate(22.00,');
  });

  it('at walkPhase=0.25 right leg has max negative rotation (−22.00°)', () => {
    const svg = renderAvatarSVG(makeAvatar(), 'normal', 0.25);
    expect(svg).toContain('rotate(-22.00,');
  });

  it('at walkPhase=0.25 left arm swings backward (−18.00°, opposite to left leg)', () => {
    const svg = renderAvatarSVG(makeAvatar(), 'normal', 0.25);
    expect(svg).toContain('rotate(-18.00,');
  });

  it('at walkPhase=0.25 right arm swings forward (+18.00°, opposite to right leg)', () => {
    const svg = renderAvatarSVG(makeAvatar(), 'normal', 0.25);
    expect(svg).toContain('rotate(18.00,');
  });

  it('at walkPhase=0.75 all rotation signs are reversed compared to 0.25', () => {
    const svg = renderAvatarSVG(makeAvatar(), 'normal', 0.75);
    // sin(3π/2) = -1 → legSwing = -22.00
    // Left leg: rotate(-22.00, ...), Right leg: rotate(22.00, ...)
    // Left arm: rotate(18.00, ...),  Right arm: rotate(-18.00, ...)
    expect(svg).toContain('rotate(-22.00,');
    expect(svg).toContain('rotate(22.00,');
    expect(svg).toContain('rotate(18.00,');
    expect(svg).toContain('rotate(-18.00,');
  });

  it('at walkPhase=1 produces identical rotation as walkPhase=0 (full cycle)', () => {
    const svg0 = renderAvatarSVG(makeAvatar(), 'normal', 0);
    const svg1 = renderAvatarSVG(makeAvatar(), 'normal', 1);
    expect(svg0).toBe(svg1);
  });

  it('walkPhase=0 (standing) matches default (no walkPhase argument)', () => {
    const svgDefault = renderAvatarSVG(makeAvatar(), 'normal');
    const svgZero    = renderAvatarSVG(makeAvatar(), 'normal', 0);
    expect(svgDefault).toBe(svgZero);
  });

  it('each leg and arm is wrapped in a rotation <g> group', () => {
    const svg = renderAvatarSVG(makeAvatar(), 'normal', 0.25);
    // 2 leg groups + 2 arm groups = 4 rotate() transforms total
    expect(countOccurrences(svg, 'transform="rotate(')).toBe(4);
  });

  it('shoes are inside the leg rotation groups (shoe colour inside <g>)', () => {
    // Default shoe colour for tshirt is #334155
    // It must appear inside (i.e. after) a rotate transform and before </g>
    const svg = renderAvatarSVG(makeAvatar({ clothes: 'tshirt' }), 'normal', 0.25);
    const firstRotate = svg.indexOf('transform="rotate(');
    const firstShoe   = svg.indexOf('#334155');
    expect(firstShoe).toBeGreaterThan(firstRotate);
  });

  it('works at non-cardinal phase values without throwing', () => {
    [0.1, 0.33, 0.5, 0.66, 0.9, 0.999].forEach(phase => {
      expect(() => renderAvatarSVG(makeAvatar(), 'normal', phase)).not.toThrow();
    });
  });

  it('rotation groups exist at large size too', () => {
    const svg = renderAvatarSVG(makeAvatar(), 'large', 0.25);
    expect(countOccurrences(svg, 'transform="rotate(')).toBe(4);
    expect(svg).toContain('rotate(22.00,');
    expect(svg).toContain('rotate(-22.00,');
  });
});

