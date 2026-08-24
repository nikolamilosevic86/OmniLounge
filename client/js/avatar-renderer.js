export const AVATAR_OPTIONS = {
  skinColors: ['#FFDBAC', '#F1C27D', '#E0AC69', '#C68642', '#8D5524', '#5C3D2E'],
  hair: ['short', 'long', 'curly', 'mohawk', 'bald', 'ponytail'],
  beards: ['none', 'stubble', 'goatee', 'full'],
  glasses: ['none', 'round', 'square', 'sunglasses'],
  clothes: ['tshirt', 'hoodie', 'suit', 'dress', 'jacket'],
  accessories: ['none', 'hat', 'backpack', 'scarf', 'headphones'],
};

const HAIR_COLORS = {
  short:    '#3b2f2f',
  long:     '#8b4513',
  curly:    '#1a0a00',
  mohawk:   '#ff3d71',
  bald:     'none',
  ponytail: '#c8860a',
};

const CLOTHES_COLORS = {
  tshirt:  '#4ecca3',
  hoodie:  '#7c3aed',
  suit:    '#1e293b',
  dress:   '#f43f5e',
  jacket:  '#0ea5e9',
};

// ─── colour helpers ────────────────────────────────────────────────────────────

function shade(hex, amt) {
  if (!hex || !hex.startsWith('#')) return hex;
  const n = parseInt(hex.slice(1), 16);
  const r = Math.min(255, Math.max(0, (n >> 16) + amt));
  const g = Math.min(255, Math.max(0, ((n >> 8) & 0xff) + amt));
  const b = Math.min(255, Math.max(0, (n & 0xff) + amt));
  return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
}

// ─── hair (back layer – drawn behind head) ────────────────────────────────────

function buildHairBack(style, w, hcx, hcy, hrx, hry, hairC) {
  if (style === 'bald') return '';
  switch (style) {
    case 'long':
      return `
        <path d="M${hcx - hrx * 0.88},${hcy - hry * 0.2}
                 Q${hcx - hrx * 1.1},${hcy + hry * 1.3} ${hcx - hrx * 0.52},${hcy + hry * 3.7}"
              stroke="${hairC}" stroke-width="${w * 0.12}" stroke-linecap="round" fill="none"/>
        <path d="M${hcx + hrx * 0.88},${hcy - hry * 0.2}
                 Q${hcx + hrx * 1.1},${hcy + hry * 1.3} ${hcx + hrx * 0.52},${hcy + hry * 3.7}"
              stroke="${hairC}" stroke-width="${w * 0.12}" stroke-linecap="round" fill="none"/>`;
    case 'ponytail':
      return `
        <path d="M${hcx + hrx * 0.8},${hcy - hry * 0.05}
                 Q${hcx + hrx * 1.38},${hcy + hry * 1.15} ${hcx + hrx * 0.58},${hcy + hry * 3.3}"
              stroke="${hairC}" stroke-width="${w * 0.1}" stroke-linecap="round" fill="none"/>`;
    default:
      return '';
  }
}

// ─── hair (front layer – drawn in front of head) ──────────────────────────────

function buildHairFront(style, w, hcx, hcy, hrx, hry, hairC) {
  if (style === 'bald') return '';
  const hl = shade(hairC, 52);
  const dk = shade(hairC, -28);

  switch (style) {
    case 'short':
      return `
        <path d="M${hcx - hrx},${hcy - hry * 0.24}
                 Q${hcx - hrx * 0.86},${hcy - hry * 1.48} ${hcx},${hcy - hry * 1.52}
                 Q${hcx + hrx * 0.86},${hcy - hry * 1.48} ${hcx + hrx},${hcy - hry * 0.24}
                 Q${hcx + hrx * 0.6},${hcy - hry * 0.54} ${hcx},${hcy - hry * 0.5}
                 Q${hcx - hrx * 0.6},${hcy - hry * 0.54} ${hcx - hrx},${hcy - hry * 0.24}Z"
              fill="${hairC}"/>
        <path d="M${hcx - hrx * 0.35},${hcy - hry * 1.42}
                 Q${hcx - hrx * 0.1},${hcy - hry * 1.2} ${hcx + hrx * 0.22},${hcy - hry * 1.34}"
              fill="none" stroke="${hl}" stroke-width="${w * 0.025}" opacity="0.52" stroke-linecap="round"/>`;

    case 'long':
      return `
        <path d="M${hcx - hrx},${hcy - hry * 0.24}
                 Q${hcx - hrx * 0.86},${hcy - hry * 1.48} ${hcx},${hcy - hry * 1.55}
                 Q${hcx + hrx * 0.86},${hcy - hry * 1.48} ${hcx + hrx},${hcy - hry * 0.24}
                 Q${hcx + hrx * 0.6},${hcy - hry * 0.54} ${hcx},${hcy - hry * 0.5}
                 Q${hcx - hrx * 0.6},${hcy - hry * 0.54} ${hcx - hrx},${hcy - hry * 0.24}Z"
              fill="${hairC}"/>
        <path d="M${hcx - hrx * 0.35},${hcy - hry * 1.42}
                 Q${hcx - hrx * 0.1},${hcy - hry * 1.2} ${hcx + hrx * 0.22},${hcy - hry * 1.34}"
              fill="none" stroke="${hl}" stroke-width="${w * 0.025}" opacity="0.52" stroke-linecap="round"/>
        <path d="M${hcx + hrx * 0.24},${hcy - hry * 1.52}
                 Q${hcx + hrx * 0.18},${hcy - hry * 0.52} ${hcx + hrx * 0.52},${hcy - hry * 0.06}"
              fill="none" stroke="${dk}" stroke-width="${w * 0.028}" opacity="0.38" stroke-linecap="round"/>`;

    case 'curly':
      return `
        <circle cx="${hcx - hrx * 0.66}" cy="${hcy - hry * 0.9}"  r="${hrx * 0.34}" fill="${hairC}"/>
        <circle cx="${hcx - hrx * 0.16}" cy="${hcy - hry * 1.22}" r="${hrx * 0.35}" fill="${hairC}"/>
        <circle cx="${hcx + hrx * 0.36}" cy="${hcy - hry * 1.18}" r="${hrx * 0.33}" fill="${hairC}"/>
        <circle cx="${hcx + hrx * 0.78}" cy="${hcy - hry * 0.86}" r="${hrx * 0.31}" fill="${hairC}"/>
        <circle cx="${hcx - hrx * 0.93}" cy="${hcy - hry * 0.34}" r="${hrx * 0.29}" fill="${hairC}"/>
        <circle cx="${hcx + hrx * 0.93}" cy="${hcy - hry * 0.34}" r="${hrx * 0.29}" fill="${hairC}"/>
        <circle cx="${hcx + hrx * 0.55}" cy="${hcy - hry * 1.44}" r="${hrx * 0.26}" fill="${dk}"/>
        <circle cx="${hcx - hrx * 0.37}" cy="${hcy - hry * 1.38}" r="${hrx * 0.26}" fill="${dk}"/>
        <circle cx="${hcx - hrx * 0.66}" cy="${hcy - hry * 0.9}"  r="${hrx * 0.12}" fill="${hl}" opacity="0.52"/>
        <circle cx="${hcx + hrx * 0.36}" cy="${hcy - hry * 1.18}" r="${hrx * 0.1}"  fill="${hl}" opacity="0.52"/>`;

    case 'mohawk':
      return `
        <path d="M${hcx - hrx * 0.2},${hcy - hry * 0.65}
                 L${hcx - hrx * 0.14},${hcy - hry * 2.2}
                 L${hcx},${hcy - hry * 2.45}
                 L${hcx + hrx * 0.14},${hcy - hry * 2.2}
                 L${hcx + hrx * 0.2},${hcy - hry * 0.65}Z"
              fill="${hairC}"/>
        <path d="M${hcx - hrx * 0.08},${hcy - hry * 0.72}
                 L${hcx - hrx * 0.04},${hcy - hry * 2.12}
                 L${hcx + hrx * 0.06},${hcy - hry * 2.06}
                 L${hcx + hrx * 0.06},${hcy - hry * 0.68}Z"
              fill="${hl}" opacity="0.42"/>`;

    case 'ponytail':
      return `
        <path d="M${hcx - hrx},${hcy - hry * 0.24}
                 Q${hcx - hrx * 0.86},${hcy - hry * 1.48} ${hcx},${hcy - hry * 1.52}
                 Q${hcx + hrx * 0.86},${hcy - hry * 1.48} ${hcx + hrx},${hcy - hry * 0.24}
                 Q${hcx + hrx * 0.6},${hcy - hry * 0.54} ${hcx},${hcy - hry * 0.5}
                 Q${hcx - hrx * 0.6},${hcy - hry * 0.54} ${hcx - hrx},${hcy - hry * 0.24}Z"
              fill="${hairC}"/>
        <circle cx="${hcx + hrx * 0.74}" cy="${hcy - hry * 0.1}" r="${hrx * 0.14}" fill="${dk}"/>
        <path d="M${hcx - hrx * 0.35},${hcy - hry * 1.42}
                 Q${hcx - hrx * 0.1},${hcy - hry * 1.2} ${hcx + hrx * 0.22},${hcy - hry * 1.34}"
              fill="none" stroke="${hl}" stroke-width="${w * 0.025}" opacity="0.52" stroke-linecap="round"/>`;

    default:
      return '';
  }
}

// ─── beard ────────────────────────────────────────────────────────────────────

function buildBeard(style, w, hcx, hcy, hrx, hry, skin) {
  const mBot = hcy + hry * 0.54;
  const bc   = '#3b2f2f';
  switch (style) {
    case 'stubble':
      return `<ellipse cx="${hcx}" cy="${mBot + hry * 0.09}" rx="${hrx * 0.56}" ry="${hry * 0.19}" fill="${bc}" opacity="0.17"/>`;
    case 'goatee':
      return `<path d="M${hcx - hrx * 0.25},${mBot}
                      Q${hcx},${mBot + hry * 0.55} ${hcx + hrx * 0.25},${mBot}Z"
                   fill="${bc}" opacity="0.88"/>`;
    case 'full':
      return `
        <path d="M${hcx - hrx * 0.77},${mBot - hry * 0.08}
                 Q${hcx - hrx * 0.9},${mBot + hry * 0.52} ${hcx - hrx * 0.43},${mBot + hry * 0.68}
                 Q${hcx},${mBot + hry * 0.85} ${hcx + hrx * 0.43},${mBot + hry * 0.68}
                 Q${hcx + hrx * 0.9},${mBot + hry * 0.52} ${hcx + hrx * 0.77},${mBot - hry * 0.08}
                 Q${hcx + hrx * 0.5},${mBot + hry * 0.33} ${hcx},${mBot + hry * 0.31}
                 Q${hcx - hrx * 0.5},${mBot + hry * 0.33} ${hcx - hrx * 0.77},${mBot - hry * 0.08}Z"
              fill="${bc}" opacity="0.9"/>
        <path d="M${hcx - hrx * 0.21},${mBot + hry * 0.07}
                 Q${hcx},${mBot + hry * 0.4} ${hcx + hrx * 0.21},${mBot + hry * 0.07}"
              fill="none" stroke="${skin}" stroke-width="${w * 0.022}" opacity="0.45"/>`;
    default:
      return '';
  }
}

// ─── glasses ─────────────────────────────────────────────────────────────────

function buildGlasses(style, w, hcx, eyeY, eSpr, eRX, eRY) {
  if (style === 'none') return '';
  const lx  = hcx - eSpr;
  const rx  = hcx + eSpr;
  const fr  = eRX * 1.34;
  const fry = eRY * 1.3;

  switch (style) {
    case 'round':
      return `
        <circle cx="${lx}" cy="${eyeY}" r="${fr}"
                fill="rgba(200,230,255,0.11)" stroke="#1e293b" stroke-width="${w * 0.033}"/>
        <circle cx="${rx}" cy="${eyeY}" r="${fr}"
                fill="rgba(200,230,255,0.11)" stroke="#1e293b" stroke-width="${w * 0.033}"/>
        <line x1="${lx + fr}" y1="${eyeY}" x2="${rx - fr}" y2="${eyeY}"
              stroke="#1e293b" stroke-width="${w * 0.028}"/>
        <line x1="${lx - fr}"         y1="${eyeY}"           x2="${lx - fr - w * 0.072}" y2="${eyeY + eRY * 0.65}"
              stroke="#1e293b" stroke-width="${w * 0.028}"/>
        <line x1="${rx + fr}"         y1="${eyeY}"           x2="${rx + fr + w * 0.072}" y2="${eyeY + eRY * 0.65}"
              stroke="#1e293b" stroke-width="${w * 0.028}"/>
        <path d="M${lx - fr * 0.76},${eyeY - fry * 0.56}
                 Q${lx},${eyeY - fry * 0.88} ${lx + fr * 0.76},${eyeY - fry * 0.56}"
             fill="none" stroke="rgba(255,255,255,0.22)" stroke-width="${w * 0.018}"/>
        <path d="M${rx - fr * 0.76},${eyeY - fry * 0.56}
                 Q${rx},${eyeY - fry * 0.88} ${rx + fr * 0.76},${eyeY - fry * 0.56}"
             fill="none" stroke="rgba(255,255,255,0.22)" stroke-width="${w * 0.018}"/>`;

    case 'square':
      return `
        <rect x="${lx - fr}" y="${eyeY - fry}" width="${fr * 2}" height="${fry * 2}"
              rx="${fr * 0.2}" fill="rgba(200,230,255,0.1)" stroke="#1e293b" stroke-width="${w * 0.033}"/>
        <rect x="${rx - fr}" y="${eyeY - fry}" width="${fr * 2}" height="${fry * 2}"
              rx="${fr * 0.2}" fill="rgba(200,230,255,0.1)" stroke="#1e293b" stroke-width="${w * 0.033}"/>
        <line x1="${lx + fr}" y1="${eyeY}" x2="${rx - fr}" y2="${eyeY}"
              stroke="#1e293b" stroke-width="${w * 0.028}"/>
        <line x1="${lx - fr}"         y1="${eyeY}"           x2="${lx - fr - w * 0.072}" y2="${eyeY + eRY * 0.65}"
              stroke="#1e293b" stroke-width="${w * 0.028}"/>
        <line x1="${rx + fr}"         y1="${eyeY}"           x2="${rx + fr + w * 0.072}" y2="${eyeY + eRY * 0.65}"
              stroke="#1e293b" stroke-width="${w * 0.028}"/>`;

    case 'sunglasses':
      return `
        <path d="M${lx - fr * 1.12},${eyeY - fry * 0.76}
                 Q${lx - fr * 0.88},${eyeY - fry * 1.2} ${lx},${eyeY - fry * 1.14}
                 Q${lx + fr * 0.88},${eyeY - fry * 1.2} ${lx + fr * 1.12},${eyeY - fry * 0.76}
                 L${lx + fr * 1.06},${eyeY + fry * 0.64}
                 Q${lx},${eyeY + fry * 0.94} ${lx - fr * 1.06},${eyeY + fry * 0.64}Z"
              fill="#0f172a" opacity="0.9"/>
        <path d="M${rx - fr * 1.12},${eyeY - fry * 0.76}
                 Q${rx - fr * 0.88},${eyeY - fry * 1.2} ${rx},${eyeY - fry * 1.14}
                 Q${rx + fr * 0.88},${eyeY - fry * 1.2} ${rx + fr * 1.12},${eyeY - fry * 0.76}
                 L${rx + fr * 1.06},${eyeY + fry * 0.64}
                 Q${rx},${eyeY + fry * 0.94} ${rx - fr * 1.06},${eyeY + fry * 0.64}Z"
              fill="#0f172a" opacity="0.9"/>
        <line x1="${lx + fr * 1.12}" y1="${eyeY}" x2="${rx - fr * 1.12}" y2="${eyeY}"
              stroke="#0f172a" stroke-width="${w * 0.036}"/>
        <line x1="${lx - fr * 1.12}" y1="${eyeY - fry * 0.42}" x2="${lx - fr * 1.34}" y2="${eyeY + fry * 0.52}"
              stroke="#0f172a" stroke-width="${w * 0.03}"/>
        <line x1="${rx + fr * 1.12}" y1="${eyeY - fry * 0.42}" x2="${rx + fr * 1.34}" y2="${eyeY + fry * 0.52}"
              stroke="#0f172a" stroke-width="${w * 0.03}"/>
        <path d="M${lx - fr * 0.82},${eyeY - fry * 0.62}
                 Q${lx},${eyeY - fry * 0.94} ${lx + fr * 0.82},${eyeY - fry * 0.62}"
             fill="none" stroke="rgba(255,255,255,0.24)" stroke-width="${w * 0.02}"/>
        <path d="M${rx - fr * 0.82},${eyeY - fry * 0.62}
                 Q${rx},${eyeY - fry * 0.94} ${rx + fr * 0.82},${eyeY - fry * 0.62}"
             fill="none" stroke="rgba(255,255,255,0.24)" stroke-width="${w * 0.02}"/>`;

    default:
      return '';
  }
}

// ─── accessories ─────────────────────────────────────────────────────────────

function buildAccessory(style, w, h, hcx, hcy, hrx, hry, bodyTop, bodyBot, clothC) {
  switch (style) {

    case 'hat': {
      const hc      = '#1e293b';
      const brimY   = hcy - hry * 1.1;
      const crownW  = hrx * 0.9;
      const crownH  = hry * 1.12;
      return {
        back: '',
        front: `
          <rect x="${hcx - crownW}" y="${brimY - crownH}" width="${crownW * 2}" height="${crownH}"
                rx="${crownW * 0.1}" fill="${hc}"/>
          <ellipse cx="${hcx}" cy="${brimY}" rx="${hrx * 1.24}" ry="${hry * 0.145}" fill="${hc}"/>
          <rect x="${hcx - crownW * 0.88}" y="${brimY - crownH}" width="${crownW * 0.42}" height="${crownH}"
                rx="${crownW * 0.05}" fill="${shade(hc, 26)}" opacity="0.22"/>
          <rect x="${hcx - crownW}" y="${brimY - crownH * 0.38}" width="${crownW * 2}" height="${crownH * 0.14}"
                fill="#e11d48" opacity="0.82"/>`,
      };
    }

    case 'headphones': {
      const hpc = '#1e293b';
      const acc = '#6366f1';
      const elX = hcx - hrx * 1.06;
      const erX = hcx + hrx * 1.06;
      const eY  = hcy - hry * 0.1;
      const epW = w * 0.1;
      const epH = hry * 0.54;
      return {
        back: '',
        front: `
          <path d="M${elX + epW * 0.5},${eY - hry * 0.44}
                   Q${hcx},${hcy - hry * 1.75} ${erX - epW * 0.5},${eY - hry * 0.44}"
                fill="none" stroke="${hpc}" stroke-width="${w * 0.06}"/>
          <rect x="${elX - epW * 0.12}" y="${eY - hry * 0.42}" width="${epW}" height="${epH}"
                rx="${epW * 0.36}" fill="${hpc}"/>
          <rect x="${erX - epW * 0.88}" y="${eY - hry * 0.42}" width="${epW}" height="${epH}"
                rx="${epW * 0.36}" fill="${hpc}"/>
          <rect x="${elX - epW * 0.05}" y="${eY - hry * 0.32}" width="${epW * 0.74}" height="${epH * 0.7}"
                rx="${epW * 0.26}" fill="${acc}"/>
          <rect x="${erX - epW * 0.69}" y="${eY - hry * 0.32}" width="${epW * 0.74}" height="${epH * 0.7}"
                rx="${epW * 0.26}" fill="${acc}"/>`,
      };
    }

    case 'scarf': {
      const sc  = '#f43f5e';
      const scHL = shade(sc, 36);
      const scDK = shade(sc, -30);
      const sy   = bodyTop - hry * 0.06;
      return {
        back: '',
        front: `
          <path d="M${hcx - hrx * 0.84},${sy}
                   Q${hcx},${sy + hry * 0.34} ${hcx + hrx * 0.84},${sy}
                   L${hcx + hrx * 0.78},${sy + hry * 0.31}
                   Q${hcx},${sy + hry * 0.54} ${hcx - hrx * 0.78},${sy + hry * 0.31}Z"
                fill="${sc}"/>
          <path d="M${hcx - hrx * 0.2},${sy + hry * 0.19}
                   L${hcx - hrx * 0.24},${sy + hry * 0.84}
                   L${hcx + hrx * 0.24},${sy + hry * 0.72}"
                fill="none" stroke="${scDK}" stroke-width="${w * 0.067}" stroke-linecap="round"/>
          <path d="M${hcx - hrx * 0.6},${sy + hry * 0.03}
                   Q${hcx},${sy + hry * 0.27} ${hcx + hrx * 0.6},${sy + hry * 0.03}"
                fill="none" stroke="${scHL}" stroke-width="${w * 0.022}" opacity="0.52"/>`,
      };
    }

    case 'backpack': {
      const bpc  = shade(clothC, -55);
      const bpHL = shade(clothC, -22);
      const bpW  = w * 0.24;
      const bodyH = bodyBot - bodyTop;
      const bpH  = bodyH * 0.76;
      const bpX  = hcx + (w * 0.52) / 2 - w * 0.02;
      const bpY  = bodyTop + bodyH * 0.07;
      return {
        back: `
          <rect x="${bpX}" y="${bpY}" width="${bpW}" height="${bpH}" rx="${bpW * 0.22}" fill="${bpc}"/>
          <rect x="${bpX + bpW * 0.12}" y="${bpY + bpH * 0.1}" width="${bpW * 0.76}" height="${bpH * 0.4}"
                rx="${bpW * 0.12}" fill="${bpHL}" opacity="0.7"/>
          <rect x="${bpX + bpW * 0.28}" y="${bpY + bpH * 0.56}" width="${bpW * 0.44}" height="${bpH * 0.28}"
                rx="${bpW * 0.1}" fill="${bpHL}" opacity="0.6"/>
          <ellipse cx="${bpX + bpW * 0.5}" cy="${bpY + bpH * 0.7}" rx="${bpW * 0.1}" ry="${bpH * 0.057}"
                   fill="${shade(bpc, 24)}" opacity="0.84"/>`,
        front: `
          <path d="M${bpX + bpW * 0.15},${bpY + bpH * 0.1}
                   Q${hcx + w * 0.12},${bodyTop + bodyH * 0.09} ${hcx + w * 0.1},${bodyTop + bodyH * 0.36}"
                fill="none" stroke="${bpHL}" stroke-width="${w * 0.032}" opacity="0.8"/>
          <path d="M${bpX + bpW * 0.15},${bpY + bpH * 0.45}
                   Q${hcx + w * 0.1},${bodyTop + bodyH * 0.49} ${hcx + w * 0.08},${bodyTop + bodyH * 0.67}"
                fill="none" stroke="${bpHL}" stroke-width="${w * 0.028}" opacity="0.7"/>`,
      };
    }

    default:
      return { back: '', front: '' };
  }
}

// ─── main render ─────────────────────────────────────────────────────────────

const MAX_LEG_ANGLE = 22;
const MAX_ARM_ANGLE = 18;

export function renderAvatarSVG(avatar, size = 'normal', walkPhase = 0, talking = false, actionState = null, blocking = false, attackAngles = null) {
  const w = size === 'large' ? 120 : 60;
  const h = size === 'large' ? 180 : 90;

  const skin    = avatar.skinColor || '#FFDBAC';
  const skinDk  = shade(skin, -30);
  const skinLt  = shade(skin, 24);
  const hairC   = HAIR_COLORS[avatar.hair] || '#3b2f2f';
  const clothC  = CLOTHES_COLORS[avatar.clothes] || '#4ecca3';
  const clothDk = shade(clothC, -38);
  const clothHL = shade(clothC, 40);

  // ── head geometry ──────────────────────────────────────────────────────────
  const hcx = w * 0.5;
  const hcy = h * 0.215;
  const hrx = w * 0.25;
  const hry = h * 0.2;

  // ── neck ───────────────────────────────────────────────────────────────────
  const neckW   = w * 0.116;
  const neckTop = hcy + hry - h * 0.026;
  const neckH   = h * 0.054;

  // ── body ───────────────────────────────────────────────────────────────────
  const bodyTop = neckTop + neckH - h * 0.013;
  const bodyBot = h * 0.668;
  const bodyW   = w * 0.52;
  const bL      = hcx - bodyW / 2;
  const bodyH   = bodyBot - bodyTop;

  // ── arms ───────────────────────────────────────────────────────────────────
  const armW   = w * 0.13;
  const armH   = h * 0.258;
  const armTop = bodyTop + h * 0.008;
  const lAX    = bL - armW * 0.66;
  const rAX    = bL + bodyW - armW * 0.34;

  // ── legs ───────────────────────────────────────────────────────────────────
  const legW   = w * 0.138;
  const legH   = h * 0.258;
  const legGap = w * 0.028;
  const legTop = bodyBot - h * 0.013;
  const lLX    = hcx - legGap / 2 - legW;
  const rLX    = hcx + legGap / 2;

  // ── shoes ──────────────────────────────────────────────────────────────────
  const shoeY = legTop + legH + h * 0.008;
  const shoeC = avatar.clothes === 'suit'  ? '#0f172a'
              : avatar.clothes === 'dress' ? '#be185d'
              : '#334155';
  const lSX = lLX + legW * 0.5;
  const rSX = rLX + legW * 0.5;

  // ── eye geometry ───────────────────────────────────────────────────────────
  const eyeY = hcy - hry * 0.055;
  const eSpr = hrx * 0.465;
  const eRX  = hrx * 0.218;
  const eRY  = hry * 0.288;
  const lEX  = hcx - eSpr;
  const rEX  = hcx + eSpr;

  // Iris colour derived from first character of username
  const EC    = ['#3b82f6', '#10b981', '#8b5cf6', '#ef4444', '#f59e0b', '#06b6d4'];
  const irisC = EC[((avatar.username || '').charCodeAt(0) || 0) % EC.length];

  // Leg colour
  const legC  = avatar.clothes === 'dress' ? shade('#f43f5e', -15)
              : avatar.clothes === 'suit'  ? '#0f172a'
              : shade(clothC, -45);
  const legHL = shade(legC, 36);

  // ── Walk swing angles (formatted to 2dp for deterministic test assertions) ────
  const sinP  = Math.sin(walkPhase * Math.PI * 2);
  // Guard against -0.00 from floating-point sin(2π) ≈ -2.4e-16
  const _fmt  = (n) => Object.is(n.toFixed(2), '-0.00') ? '0.00' : n.toFixed(2);
  const ls    = _fmt(sinP * MAX_LEG_ANGLE);           // left-leg swing
  const negLs = _fmt(-parseFloat(ls));                // right-leg swing
  const as_   = _fmt(sinP * MAX_ARM_ANGLE);           // right-arm swing
  const negAs = _fmt(-parseFloat(as_));               // left-arm swing

  // Hip & shoulder pivot x-coordinates
  const lHipX = (lLX + legW * 0.5).toFixed(3);
  const rHipX = (rLX + legW * 0.5).toFixed(3);
  const hipY  = legTop.toFixed(3);
  const lShoX = (lAX + armW * 0.5).toFixed(3);
  const rShoX = (rAX + armW * 0.5).toFixed(3);
  const shoY  = armTop.toFixed(3);

  // ── SVG fragments — vary by actionState ───────────────────────────────────

  const svgShadow = `
    <ellipse cx="${hcx}" cy="${h * 0.978}" rx="${w * 0.28}" ry="${h * 0.022}"
             fill="rgba(0,0,0,0.18)"/>`;

  // ── Legs ──────────────────────────────────────────────────────────────────
  const isSitting = actionState === 'sitting' || actionState === 'lounging';
  let svgLegs;

  if (isSitting) {
    // Bent-leg pose: thighs go outward, shins hang down
    const seatY    = bodyBot;
    const thighLen = legH * 0.52;
    const thighH   = legW * 0.96;
    const shinH    = legH * 0.44;
    const lThighX  = hcx - legGap * 0.5 - thighLen;
    const rThighX  = hcx + legGap * 0.5;
    const lShinX   = lThighX + legW * 0.05;
    const rShinX   = rThighX + thighLen - legW;
    const shinY    = seatY + thighH * 0.5 - h * 0.012;

    svgLegs = `
      <rect x="${lThighX}" y="${seatY - thighH * 0.5}" width="${thighLen}" height="${thighH}"
            rx="${thighH * 0.46}" fill="${legC}"/>
      <rect x="${lThighX}" y="${seatY - thighH * 0.48}" width="${thighLen * 0.38}" height="${thighH * 0.88}"
            rx="${thighH * 0.35}" fill="${legHL}" opacity="0.28"/>
      <rect x="${lShinX}" y="${shinY}" width="${legW}" height="${shinH}" rx="${legW * 0.46}" fill="${legC}"/>
      <ellipse cx="${lShinX + legW * 0.5}" cy="${shinY + shinH}" rx="${legW * 0.6}" ry="${h * 0.03}" fill="${shoeC}"/>

      <rect x="${rThighX}" y="${seatY - thighH * 0.5}" width="${thighLen}" height="${thighH}"
            rx="${thighH * 0.46}" fill="${legC}"/>
      <rect x="${rThighX}" y="${seatY - thighH * 0.48}" width="${thighLen * 0.38}" height="${thighH * 0.88}"
            rx="${thighH * 0.35}" fill="${legHL}" opacity="0.28"/>
      <rect x="${rShinX}" y="${shinY}" width="${legW}" height="${shinH}" rx="${legW * 0.46}" fill="${legC}"/>
      <ellipse cx="${rShinX + legW * 0.5}" cy="${shinY + shinH}" rx="${legW * 0.6}" ry="${h * 0.03}" fill="${shoeC}"/>`;
  } else {
    // Normal walking legs — override with attack angles if present
    const leftLegAngle  = attackAngles ? attackAngles.leftLegAngle.toFixed(2)  : ls;
    const rightLegAngle = attackAngles ? attackAngles.rightLegAngle.toFixed(2) : negLs;
    svgLegs = `
      <g transform="rotate(${leftLegAngle}, ${lHipX}, ${hipY})">
        <rect x="${lLX}" y="${legTop}" width="${legW}" height="${legH}" rx="${legW * 0.46}"
              fill="${legC}"/>
        <rect x="${lLX + legW * 0.17}" y="${legTop + legH * 0.04}" width="${legW * 0.24}" height="${legH * 0.58}"
              rx="${legW * 0.12}" fill="${legHL}" opacity="0.3"/>
        <ellipse cx="${lSX - legW * 0.07}" cy="${shoeY}" rx="${legW * 0.64}" ry="${h * 0.034}"
                 fill="${shoeC}"/>
        <ellipse cx="${lSX - legW * 0.14}" cy="${shoeY - h * 0.004}" rx="${legW * 0.56}" ry="${h * 0.022}"
                 fill="${shade(shoeC, 30)}"/>
      </g>
      <g transform="rotate(${rightLegAngle}, ${rHipX}, ${hipY})">
        <rect x="${rLX}" y="${legTop}" width="${legW}" height="${legH}" rx="${legW * 0.46}"
              fill="${legC}"/>
        <rect x="${rLX + legW * 0.17}" y="${legTop + legH * 0.04}" width="${legW * 0.24}" height="${legH * 0.58}"
              rx="${legW * 0.12}" fill="${legHL}" opacity="0.3"/>
        <ellipse cx="${rSX + legW * 0.07}" cy="${shoeY}" rx="${legW * 0.64}" ry="${h * 0.034}"
                 fill="${shoeC}"/>
        <ellipse cx="${rSX + legW * 0.14}" cy="${shoeY - h * 0.004}" rx="${legW * 0.56}" ry="${h * 0.022}"
                 fill="${shade(shoeC, 30)}"/>
      </g>`;
  }

  // ── Arms ──────────────────────────────────────────────────────────────────
  // Blocking: both arms swing up into a guard; otherwise normal walk swing.
  let lArmRot = negAs;
  let rArmRot = as_;
  if (attackAngles) {
    lArmRot = attackAngles.leftArmAngle.toFixed(2);
    rArmRot = attackAngles.rightArmAngle.toFixed(2);
  } else if (blocking && !isSitting) {
    lArmRot = '-42.00';
    rArmRot = '42.00';
  } else if (actionState === 'drinking') {
    rArmRot = '-55.00';
  }
  const rArmPivX = rShoX;
  const rArmPivY = shoY;

  let drinkingExtra = '';
  if (actionState === 'drinking') {
    // Coffee cup near raised right hand
    const cupBaseX = rAX + armW * 0.5;
    const cupBaseY = armTop + armH * 0.2;
    drinkingExtra = `
      <rect x="${cupBaseX - w * 0.044}" y="${cupBaseY - h * 0.052}" width="${w * 0.088}" height="${h * 0.072}"
            rx="${w * 0.012}" fill="#e8e0d0"/>
      <ellipse cx="${cupBaseX}" cy="${cupBaseY - h * 0.05}" rx="${w * 0.036}" ry="${h * 0.014}" fill="#6b3010"/>
      <path d="M${cupBaseX + w * 0.044},${cupBaseY - h * 0.038}
               a${w * 0.024},${h * 0.024} 0 0,1 0,${h * 0.034}"
            fill="none" stroke="#d0c8b8" stroke-width="${w * 0.016}" stroke-linecap="round"/>`;
  }

  let djExtra = '';
  if (actionState === 'djing') {
    // Headphone dot + music note near the avatar
    djExtra = `
      <text x="${hcx + hrx * 0.72}" y="${hcy - hry * 0.35}" font-size="${w * 0.22}" text-anchor="middle"
            fill="#c084fc" opacity="0.88" font-family="sans-serif">♪</text>
      <text x="${hcx - hrx * 0.58}" y="${hcy - hry * 0.6}" font-size="${w * 0.18}" text-anchor="middle"
            fill="#67e8f9" opacity="0.78" font-family="sans-serif">♫</text>`;
  }

  const svgArms = `
    <g transform="rotate(${lArmRot}, ${lShoX}, ${shoY})">
      <rect x="${lAX}" y="${armTop}" width="${armW}" height="${armH}" rx="${armW * 0.48}"
            fill="${clothC}"/>
      <rect x="${lAX + armW * 0.18}" y="${armTop + armH * 0.04}" width="${armW * 0.28}" height="${armH * 0.62}"
            rx="${armW * 0.1}" fill="${clothHL}" opacity="0.26"/>
      <ellipse cx="${lAX + armW * 0.5}" cy="${armTop + armH + h * 0.002}" rx="${armW * 0.46}" ry="${h * 0.03}"
               fill="${skin}"/>
      <ellipse cx="${lAX + armW * 0.5}" cy="${armTop + armH}" rx="${armW * 0.36}" ry="${h * 0.02}"
               fill="${skinDk}" opacity="0.25"/>
    </g>
    <g transform="rotate(${rArmRot}, ${rShoX}, ${shoY})">
      <rect x="${rAX}" y="${armTop}" width="${armW}" height="${armH}" rx="${armW * 0.48}"
            fill="${clothC}"/>
      <rect x="${rAX + armW * 0.18}" y="${armTop + armH * 0.04}" width="${armW * 0.28}" height="${armH * 0.62}"
            rx="${armW * 0.1}" fill="${clothHL}" opacity="0.26"/>
      <ellipse cx="${rAX + armW * 0.5}" cy="${armTop + armH + h * 0.002}" rx="${armW * 0.46}" ry="${h * 0.03}"
               fill="${skin}"/>
      <ellipse cx="${rAX + armW * 0.5}" cy="${armTop + armH}" rx="${armW * 0.36}" ry="${h * 0.02}"
               fill="${skinDk}" opacity="0.25"/>
    </g>
    ${drinkingExtra}
    ${djExtra}`;

  // Body — trapezoid (body-shaped), flared for dress
  let svgBody = '';
  if (avatar.clothes === 'dress') {
    const spread = bodyW * 0.3;
    svgBody = `
      <path d="M${bL + bodyW * 0.1},${bodyTop}
               L${bL - spread},${bodyBot}
               L${bL + bodyW + spread},${bodyBot}
               L${bL + bodyW - bodyW * 0.1},${bodyTop}Z"
            fill="${clothC}"/>
      <path d="M${bL + bodyW * 0.18},${bodyTop}
               Q${bL + bodyW * 0.12},${bodyTop + bodyH * 0.56} ${bL + bodyW * 0.06 - spread * 0.38},${bodyBot}"
            fill="${clothHL}" opacity="0.26" stroke="none"/>`;
  } else {
    svgBody = `
      <path d="M${bL + bodyW * 0.08},${bodyTop}
               Q${bL},${bodyTop + bodyH * 0.42} ${bL},${bodyBot}
               L${bL + bodyW},${bodyBot}
               Q${bL + bodyW},${bodyTop + bodyH * 0.42} ${bL + bodyW - bodyW * 0.08},${bodyTop}Z"
            fill="${clothC}"/>
      <path d="M${bL + bodyW * 0.2},${bodyTop}
               Q${bL + bodyW * 0.1},${bodyTop + bodyH * 0.56} ${bL + bodyW * 0.12},${bodyBot}"
            fill="${clothHL}" opacity="0.24" stroke="none"/>`;
  }

  // Per-clothes decorative details
  let svgClothDetail = '';
  if (avatar.clothes === 'suit') {
    svgClothDetail = `
      <path d="M${hcx - bodyW * 0.14},${bodyTop}
               L${hcx},${bodyTop + bodyH * 0.44}
               L${hcx + bodyW * 0.14},${bodyTop}"
           fill="white" opacity="0.92"/>
      <rect x="${hcx - bodyW * 0.038}" y="${bodyTop + bodyH * 0.08}" width="${bodyW * 0.076}" height="${bodyH * 0.54}"
            rx="${bodyW * 0.02}" fill="#dc2626"/>`;
  } else if (avatar.clothes === 'hoodie') {
    svgClothDetail = `
      <rect x="${hcx - bodyW * 0.17}" y="${bodyBot - bodyH * 0.32}" width="${bodyW * 0.34}" height="${bodyH * 0.3}"
            rx="${bodyW * 0.07}" fill="${clothDk}" opacity="0.4"/>
      <ellipse cx="${hcx}" cy="${bodyBot - bodyH * 0.1}" rx="${bodyW * 0.09}" ry="${bodyH * 0.065}"
               fill="${clothDk}" opacity="0.38"/>`;
  } else if (avatar.clothes === 'jacket') {
    svgClothDetail = `
      <line x1="${hcx - bodyW * 0.1}" y1="${bodyTop}" x2="${hcx - bodyW * 0.08}" y2="${bodyBot}"
            stroke="${clothDk}" stroke-width="${w * 0.023}"/>
      <line x1="${hcx + bodyW * 0.1}" y1="${bodyTop}" x2="${hcx + bodyW * 0.08}" y2="${bodyBot}"
            stroke="${clothDk}" stroke-width="${w * 0.023}"/>
      <line x1="${hcx - bodyW * 0.16}" y1="${bodyTop + bodyH * 0.36}"
            x2="${hcx + bodyW * 0.16}" y2="${bodyTop + bodyH * 0.36}"
            stroke="${clothDk}" stroke-width="${w * 0.018}" opacity="0.5"/>`;
  } else if (avatar.clothes === 'tshirt') {
    svgClothDetail = `
      <path d="M${hcx - bodyW * 0.13},${bodyTop}
               Q${hcx},${bodyTop + bodyH * 0.16} ${hcx + bodyW * 0.13},${bodyTop}"
           fill="none" stroke="${clothDk}" stroke-width="${w * 0.026}" opacity="0.44"/>`;
  }

  // Neck
  const svgNeck = `
    <rect x="${hcx - neckW / 2}" y="${neckTop}" width="${neckW}" height="${neckH + h * 0.018}"
          rx="${neckW * 0.44}" fill="${skin}"/>
    <rect x="${hcx - neckW * 0.28}" y="${neckTop}" width="${neckW * 0.26}" height="${neckH}"
          rx="${neckW * 0.13}" fill="${skinLt}" opacity="0.3"/>`;

  // Head — large round chibi head with soft shading
  const svgHead = `
    <ellipse cx="${hcx}" cy="${hcy + hry * 0.045}" rx="${hrx}" ry="${hry}" fill="${skinDk}" opacity="0.2"/>
    <ellipse cx="${hcx}" cy="${hcy}" rx="${hrx}" ry="${hry}" fill="${skin}"/>
    <ellipse cx="${hcx - hrx * 0.28}" cy="${hcy - hry * 0.12}" rx="${hrx * 0.55}" ry="${hry * 0.45}"
             fill="${skinLt}" opacity="0.2"/>
    <ellipse cx="${hcx - hrx * 0.57}" cy="${hcy}" rx="${hrx * 0.088}" ry="${hry * 0.44}" fill="${skin}"/>
    <ellipse cx="${hcx + hrx * 0.57}" cy="${hcy}" rx="${hrx * 0.088}" ry="${hry * 0.44}" fill="${skin}"/>`;

  // Eyes — large sparkly chibi eyes with blink animation classes
  const svgEyes = `
    <g class="eye-l">
      <ellipse cx="${lEX}" cy="${eyeY}" rx="${eRX * 1.14}" ry="${eRY * 1.14}" fill="white"/>
      <ellipse cx="${lEX}" cy="${eyeY + eRY * 0.08}" rx="${eRX * 0.73}" ry="${eRY * 0.84}" fill="${irisC}"/>
      <ellipse cx="${lEX}" cy="${eyeY + eRY * 0.13}" rx="${eRX * 0.4}" ry="${eRY * 0.48}" fill="#111"/>
      <ellipse cx="${lEX - eRX * 0.2}" cy="${eyeY - eRY * 0.26}" rx="${eRX * 0.19}" ry="${eRY * 0.23}"
               fill="white" opacity="0.9"/>
      <ellipse cx="${lEX + eRX * 0.19}" cy="${eyeY - eRY * 0.08}" rx="${eRX * 0.1}" ry="${eRY * 0.12}"
               fill="white" opacity="0.65"/>
      <path d="M${lEX - eRX * 1.16},${eyeY - eRY * 0.96}
               Q${lEX},${eyeY - eRY * 1.42} ${lEX + eRX * 1.16},${eyeY - eRY * 0.96}"
           fill="none" stroke="#1e0a00" stroke-width="${w * 0.025}" stroke-linecap="round"/>
    </g>
    <g class="eye-r">
      <ellipse cx="${rEX}" cy="${eyeY}" rx="${eRX * 1.14}" ry="${eRY * 1.14}" fill="white"/>
      <ellipse cx="${rEX}" cy="${eyeY + eRY * 0.08}" rx="${eRX * 0.73}" ry="${eRY * 0.84}" fill="${irisC}"/>
      <ellipse cx="${rEX}" cy="${eyeY + eRY * 0.13}" rx="${eRX * 0.4}" ry="${eRY * 0.48}" fill="#111"/>
      <ellipse cx="${rEX - eRX * 0.2}" cy="${eyeY - eRY * 0.26}" rx="${eRX * 0.19}" ry="${eRY * 0.23}"
               fill="white" opacity="0.9"/>
      <ellipse cx="${rEX + eRX * 0.19}" cy="${eyeY - eRY * 0.08}" rx="${eRX * 0.1}" ry="${eRY * 0.12}"
               fill="white" opacity="0.65"/>
      <path d="M${rEX - eRX * 1.16},${eyeY - eRY * 0.96}
               Q${rEX},${eyeY - eRY * 1.42} ${rEX + eRX * 1.16},${eyeY - eRY * 0.96}"
           fill="none" stroke="#1e0a00" stroke-width="${w * 0.025}" stroke-linecap="round"/>
    </g>`;

  // Rosy chibi cheeks
  const blushY   = eyeY + eRY * 1.14;
  const svgBlush = `
    <ellipse cx="${hcx - hrx * 0.53}" cy="${blushY}" rx="${hrx * 0.23}" ry="${hry * 0.104}"
             fill="#ffb3c6" opacity="0.44"/>
    <ellipse cx="${hcx + hrx * 0.53}" cy="${blushY}" rx="${hrx * 0.23}" ry="${hry * 0.104}"
             fill="#ffb3c6" opacity="0.44"/>`;

  // Tiny nose
  const noseY   = eyeY + eRY * 1.64;
  const svgNose = `
    <ellipse cx="${hcx}" cy="${noseY}" rx="${hrx * 0.072}" ry="${hry * 0.045}"
             fill="${skinDk}" opacity="0.36"/>`;

  // Cute upturned smile OR open talking mouth
  const mouthY   = noseY + hry * 0.22;
  const svgMouth = talking
    ? `<ellipse cx="${hcx}" cy="${mouthY + hry * 0.09}" rx="${hrx * 0.18}" ry="${hry * 0.14}"
               fill="#c0555a"/>
       <ellipse cx="${hcx}" cy="${mouthY + hry * 0.11}" rx="${hrx * 0.12}" ry="${hry * 0.085}"
               fill="#7a1f2e"/>`
    : `<path d="M${hcx - hrx * 0.22},${mouthY}
               Q${hcx},${mouthY + hry * 0.19} ${hcx + hrx * 0.22},${mouthY}"
           fill="none" stroke="#c0555a" stroke-width="${w * 0.027}" stroke-linecap="round"/>
       <path d="M${hcx - hrx * 0.14},${mouthY + hry * 0.03}
               Q${hcx},${mouthY + hry * 0.12} ${hcx + hrx * 0.14},${mouthY + hry * 0.03}"
           fill="#f87171" opacity="0.44"/>`;

  // ── assemble all layers ────────────────────────────────────────────────────
  const { back: accBack, front: accFront } =
    buildAccessory(avatar.accessory, w, h, hcx, hcy, hrx, hry, bodyTop, bodyBot, clothC);

  const hBack      = buildHairBack(avatar.hair, w, hcx, hcy, hrx, hry, hairC);
  const hFront     = buildHairFront(avatar.hair, w, hcx, hcy, hrx, hry, hairC);
  const svgBeard   = buildBeard(avatar.beard, w, hcx, hcy, hrx, hry, skin);
  const svgGlasses = buildGlasses(avatar.glasses, w, hcx, eyeY, eSpr, eRX, eRY);

  return `<svg class="avatar-svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" overflow="visible" xmlns="http://www.w3.org/2000/svg">
    ${svgShadow}
    ${accBack}
    ${svgLegs}
    ${svgArms}
    ${svgBody}
    ${svgClothDetail}
    ${svgNeck}
    ${hBack}
    ${svgHead}
    ${svgEyes}
    ${svgBlush}
    ${svgNose}
    ${svgMouth}
    ${svgBeard}
    ${svgGlasses}
    ${hFront}
    ${accFront}
  </svg>`;
}
