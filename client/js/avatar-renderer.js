export const AVATAR_OPTIONS = {
  skinColors: ['#FFDBAC', '#F1C27D', '#E0AC69', '#C68642', '#8D5524', '#5C3D2E'],
  gender: ['neutral', 'feminine', 'masculine'],
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

/** SVG gradient ids are document-global, so every avatar on screen needs its
 * OWN ids or the first-rendered avatar's colours would leak into all the
 * others. Derived deterministically from the avatar's appearance (rather
 * than a counter) so re-rendering the same avatar produces a byte-identical
 * string -- the room:state handler diffs avatar markup on every movement
 * tick and would otherwise churn the DOM constantly. */
function gradientKey(avatar, size) {
  const raw = [
    avatar.username || '', avatar.skinColor || '', avatar.hair || '',
    avatar.clothes || '', avatar.gender || '', size,
  ].join('|');
  let hash = 0;
  for (let i = 0; i < raw.length; i++) hash = (hash * 31 + raw.charCodeAt(i)) >>> 0;
  return hash.toString(36);
}

// ─── hair (back layer – drawn behind head) ────────────────────────────────────

function buildHairBack(style, w, hcx, hcy, hrx, hry, hairC) {
  if (style === 'bald') return '';
  const hl = shade(hairC, 46);
  switch (style) {
    // Strands stop around chest height. Anything much longer reads as two
    // curtains hanging past the knees rather than as hair.
    case 'long':
      return `
        <path d="M${hcx - hrx * 0.88},${hcy - hry * 0.2}
                 Q${hcx - hrx * 1.14},${hcy + hry * 1.0} ${hcx - hrx * 0.66},${hcy + hry * 2.15}"
              stroke="${hairC}" stroke-width="${w * 0.13}" stroke-linecap="round" fill="none"/>
        <path d="M${hcx + hrx * 0.88},${hcy - hry * 0.2}
                 Q${hcx + hrx * 1.14},${hcy + hry * 1.0} ${hcx + hrx * 0.66},${hcy + hry * 2.15}"
              stroke="${hairC}" stroke-width="${w * 0.13}" stroke-linecap="round" fill="none"/>
        <path d="M${hcx - hrx * 0.92},${hcy + hry * 0.15}
                 Q${hcx - hrx * 1.08},${hcy + hry * 1.05} ${hcx - hrx * 0.74},${hcy + hry * 1.85}"
              stroke="${hl}" stroke-width="${w * 0.026}" stroke-linecap="round" fill="none" opacity="0.5"/>`;
    case 'ponytail':
      return `
        <path d="M${hcx + hrx * 0.8},${hcy - hry * 0.05}
                 Q${hcx + hrx * 1.42},${hcy + hry * 0.95} ${hcx + hrx * 0.72},${hcy + hry * 2.25}"
              stroke="${hairC}" stroke-width="${w * 0.11}" stroke-linecap="round" fill="none"/>
        <path d="M${hcx + hrx * 0.9},${hcy + hry * 0.2}
                 Q${hcx + hrx * 1.34},${hcy + hry * 1.0} ${hcx + hrx * 0.82},${hcy + hry * 1.95}"
              stroke="${hl}" stroke-width="${w * 0.022}" stroke-linecap="round" fill="none" opacity="0.5"/>`;
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
        <path d="M${hcx - hrx * 1.02},${hcy - hry * 0.18}
                 Q${hcx - hrx * 0.92},${hcy - hry * 1.5} ${hcx},${hcy - hry * 1.54}
                 Q${hcx + hrx * 0.92},${hcy - hry * 1.5} ${hcx + hrx * 1.02},${hcy - hry * 0.18}
                 L${hcx + hrx * 0.86},${hcy - hry * 0.24}
                 Q${hcx + hrx * 0.72},${hcy - hry * 0.62} ${hcx + hrx * 0.1},${hcy - hry * 0.72}
                 Q${hcx - hrx * 0.6},${hcy - hry * 0.66} ${hcx - hrx * 0.86},${hcy - hry * 0.24}Z"
              fill="${hairC}"/>
        <path d="M${hcx - hrx * 0.5},${hcy - hry * 1.46}
                 Q${hcx + hrx * 0.16},${hcy - hry * 1.1} ${hcx + hrx * 0.2},${hcy - hry * 0.7}
                 Q${hcx - hrx * 0.3},${hcy - hry * 0.98} ${hcx - hrx * 0.86},${hcy - hry * 0.3}
                 Q${hcx - hrx * 0.98},${hcy - hry * 1.16} ${hcx - hrx * 0.5},${hcy - hry * 1.46}Z"
              fill="${dk}" opacity="0.55"/>
        <path d="M${hcx - hrx * 1.0},${hcy - hry * 0.2} L${hcx - hrx * 0.92},${hcy + hry * 0.24}
                 L${hcx - hrx * 0.78},${hcy - hry * 0.22}Z" fill="${hairC}"/>
        <path d="M${hcx + hrx * 1.0},${hcy - hry * 0.2} L${hcx + hrx * 0.92},${hcy + hry * 0.24}
                 L${hcx + hrx * 0.78},${hcy - hry * 0.22}Z" fill="${hairC}"/>
        <path d="M${hcx - hrx * 0.42},${hcy - hry * 1.44}
                 Q${hcx - hrx * 0.05},${hcy - hry * 1.24} ${hcx + hrx * 0.32},${hcy - hry * 1.3}"
              fill="none" stroke="${hl}" stroke-width="${w * 0.028}" opacity="0.6" stroke-linecap="round"/>`;

    case 'long':
      return `
        <path d="M${hcx - hrx * 1.04},${hcy - hry * 0.1}
                 Q${hcx - hrx * 0.9},${hcy - hry * 1.52} ${hcx},${hcy - hry * 1.58}
                 Q${hcx + hrx * 0.9},${hcy - hry * 1.52} ${hcx + hrx * 1.04},${hcy - hry * 0.1}
                 L${hcx + hrx * 0.88},${hcy - hry * 0.2}
                 Q${hcx + hrx * 0.66},${hcy - hry * 0.5} ${hcx + hrx * 0.06},${hcy - hry * 0.62}
                 Q${hcx - hrx * 0.62},${hcy - hry * 0.5} ${hcx - hrx * 0.88},${hcy - hry * 0.2}Z"
              fill="${hairC}"/>
        <path d="M${hcx - hrx * 0.06},${hcy - hry * 1.56}
                 Q${hcx - hrx * 0.72},${hcy - hry * 1.14} ${hcx - hrx * 0.9},${hcy - hry * 0.2}
                 L${hcx - hrx * 1.04},${hcy - hry * 0.1}
                 Q${hcx - hrx * 1.0},${hcy - hry * 1.3} ${hcx - hrx * 0.06},${hcy - hry * 1.56}Z"
              fill="${dk}" opacity="0.45"/>
        <path d="M${hcx - hrx * 0.4},${hcy - hry * 1.46}
                 Q${hcx - hrx * 0.05},${hcy - hry * 1.2} ${hcx + hrx * 0.3},${hcy - hry * 1.32}"
              fill="none" stroke="${hl}" stroke-width="${w * 0.028}" opacity="0.6" stroke-linecap="round"/>
        <path d="M${hcx + hrx * 0.22},${hcy - hry * 1.54}
                 Q${hcx + hrx * 0.14},${hcy - hry * 0.6} ${hcx + hrx * 0.56},${hcy - hry * 0.02}"
              fill="none" stroke="${dk}" stroke-width="${w * 0.03}" opacity="0.42" stroke-linecap="round"/>`;

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
        <path d="M${hcx - hrx * 1.02},${hcy - hry * 0.14}
                 Q${hcx - hrx * 0.88},${hcy - hry * 1.5} ${hcx},${hcy - hry * 1.56}
                 Q${hcx + hrx * 0.88},${hcy - hry * 1.5} ${hcx + hrx * 1.02},${hcy - hry * 0.14}
                 L${hcx + hrx * 0.86},${hcy - hry * 0.22}
                 Q${hcx + hrx * 0.6},${hcy - hry * 0.72} ${hcx},${hcy - hry * 0.82}
                 Q${hcx - hrx * 0.6},${hcy - hry * 0.72} ${hcx - hrx * 0.86},${hcy - hry * 0.22}Z"
              fill="${hairC}"/>
        <g stroke="${dk}" stroke-width="${w * 0.018}" fill="none" opacity="0.42" stroke-linecap="round">
          <path d="M${hcx - hrx * 0.62},${hcy - hry * 0.5} Q${hcx - hrx * 0.3},${hcy - hry * 1.36} ${hcx + hrx * 0.34},${hcy - hry * 1.48}"/>
          <path d="M${hcx - hrx * 0.2},${hcy - hry * 0.78} Q${hcx + hrx * 0.12},${hcy - hry * 1.3} ${hcx + hrx * 0.62},${hcy - hry * 1.3}"/>
          <path d="M${hcx + hrx * 0.28},${hcy - hry * 0.76} Q${hcx + hrx * 0.6},${hcy - hry * 1.1} ${hcx + hrx * 0.86},${hcy - hry * 0.96}"/>
        </g>
        <circle cx="${hcx + hrx * 0.82}" cy="${hcy - hry * 0.16}" r="${hrx * 0.17}" fill="${dk}"/>
        <circle cx="${hcx + hrx * 0.78}" cy="${hcy - hry * 0.22}" r="${hrx * 0.06}" fill="${hl}" opacity="0.5"/>
        <path d="M${hcx - hrx * 0.44},${hcy - hry * 1.44}
                 Q${hcx - hrx * 0.08},${hcy - hry * 1.26} ${hcx + hrx * 0.28},${hcy - hry * 1.36}"
              fill="none" stroke="${hl}" stroke-width="${w * 0.028}" opacity="0.6" stroke-linecap="round"/>`;

    default:
      return '';
  }
}

// ─── beard ────────────────────────────────────────────────────────────────────

function buildBeard(style, w, hcx, hcy, hrx, hry, skin, hairC) {
  const mBot = hcy + hry * 0.54;
  // Beard tracks the hair colour (a black-haired avatar with a chestnut beard
  // was one of the more obviously "off" details); bald falls back to dark brown.
  const bc   = hairC && hairC !== 'none' ? shade(hairC, -12) : '#3b2f2f';
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

  // Per-avatar gradient ids (see gradientKey) + the fills that reference them.
  const uid     = gradientKey(avatar, size);
  const gSkin   = `url(#sk-${uid})`;
  const gCloth  = `url(#cl-${uid})`;
  const gSleeve = `url(#sl-${uid})`;
  const gLeg    = `url(#lg-${uid})`;
  const gShadow = `url(#sh-${uid})`;
  // A hair-thin darker outline around the silhouette. Without it the flat
  // fills dissolve into similarly-toned room walls/floors; with it the
  // character reads as a distinct figure against ANY room style.
  const inkSkin  = shade(skin, -78);
  const inkCloth = shade(clothC, -70);
  const inkW     = w * 0.014;

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
  // Sits a touch below the torso top so the rounded shoulder overlaps the
  // sleeve cap (arms are drawn behind the body) rather than butting into it.
  const armTop = bodyTop + h * 0.03;
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

  // Soft radial contact shadow — a flat-opacity ellipse reads as a sticker
  // cut-out, a falloff gradient reads as the figure actually standing there.
  const svgShadow = `
    <ellipse cx="${hcx}" cy="${h * 0.978}" rx="${w * 0.3}" ry="${h * 0.026}"
             fill="${gShadow}"/>`;

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
            rx="${thighH * 0.46}" fill="${gLeg}" stroke="${shade(legC, -60)}" stroke-width="${inkW}" stroke-opacity="0.26"/>
      <rect x="${lThighX}" y="${seatY - thighH * 0.48}" width="${thighLen * 0.38}" height="${thighH * 0.88}"
            rx="${thighH * 0.35}" fill="${legHL}" opacity="0.28"/>
      <rect x="${lShinX}" y="${shinY}" width="${legW}" height="${shinH}" rx="${legW * 0.46}" fill="${gLeg}"
            stroke="${shade(legC, -60)}" stroke-width="${inkW}" stroke-opacity="0.26"/>
      <ellipse cx="${lShinX + legW * 0.5}" cy="${shinY + shinH}" rx="${legW * 0.6}" ry="${h * 0.03}" fill="${shoeC}"
               stroke="${shade(shoeC, -40)}" stroke-width="${inkW}" stroke-opacity="0.4"/>

      <rect x="${rThighX}" y="${seatY - thighH * 0.5}" width="${thighLen}" height="${thighH}"
            rx="${thighH * 0.46}" fill="${gLeg}" stroke="${shade(legC, -60)}" stroke-width="${inkW}" stroke-opacity="0.26"/>
      <rect x="${rThighX}" y="${seatY - thighH * 0.48}" width="${thighLen * 0.38}" height="${thighH * 0.88}"
            rx="${thighH * 0.35}" fill="${legHL}" opacity="0.28"/>
      <rect x="${rShinX}" y="${shinY}" width="${legW}" height="${shinH}" rx="${legW * 0.46}" fill="${gLeg}"
            stroke="${shade(legC, -60)}" stroke-width="${inkW}" stroke-opacity="0.26"/>
      <ellipse cx="${rShinX + legW * 0.5}" cy="${shinY + shinH}" rx="${legW * 0.6}" ry="${h * 0.03}" fill="${shoeC}"
               stroke="${shade(shoeC, -40)}" stroke-width="${inkW}" stroke-opacity="0.4"/>`;
  } else {
    // Normal walking legs — override with attack angles if present
    const leftLegAngle  = attackAngles ? attackAngles.leftLegAngle.toFixed(2)  : ls;
    const rightLegAngle = attackAngles ? attackAngles.rightLegAngle.toFixed(2) : negLs;
    svgLegs = `
      <g transform="rotate(${leftLegAngle}, ${lHipX}, ${hipY})">
        <rect x="${lLX}" y="${legTop}" width="${legW}" height="${legH}" rx="${legW * 0.46}"
              fill="${gLeg}" stroke="${shade(legC, -60)}" stroke-width="${inkW}" stroke-opacity="0.26"/>
        <rect x="${lLX + legW * 0.17}" y="${legTop + legH * 0.04}" width="${legW * 0.24}" height="${legH * 0.58}"
              rx="${legW * 0.12}" fill="${legHL}" opacity="0.3"/>
        <rect x="${lLX}" y="${legTop + legH * 0.82}" width="${legW}" height="${legH * 0.1}"
              rx="${legW * 0.2}" fill="${shade(legC, -34)}" opacity="0.55"/>
        <ellipse cx="${lSX - legW * 0.07}" cy="${shoeY}" rx="${legW * 0.64}" ry="${h * 0.034}"
                 fill="${shoeC}" stroke="${shade(shoeC, -40)}" stroke-width="${inkW}" stroke-opacity="0.4"/>
        <ellipse cx="${lSX - legW * 0.14}" cy="${shoeY - h * 0.004}" rx="${legW * 0.56}" ry="${h * 0.022}"
                 fill="${shade(shoeC, 30)}"/>
        <ellipse cx="${lSX - legW * 0.24}" cy="${shoeY - h * 0.009}" rx="${legW * 0.26}" ry="${h * 0.008}"
                 fill="${shade(shoeC, 78)}" opacity="0.5"/>
      </g>
      <g transform="rotate(${rightLegAngle}, ${rHipX}, ${hipY})">
        <rect x="${rLX}" y="${legTop}" width="${legW}" height="${legH}" rx="${legW * 0.46}"
              fill="${gLeg}" stroke="${shade(legC, -60)}" stroke-width="${inkW}" stroke-opacity="0.26"/>
        <rect x="${rLX + legW * 0.17}" y="${legTop + legH * 0.04}" width="${legW * 0.24}" height="${legH * 0.58}"
              rx="${legW * 0.12}" fill="${legHL}" opacity="0.3"/>
        <rect x="${rLX}" y="${legTop + legH * 0.82}" width="${legW}" height="${legH * 0.1}"
              rx="${legW * 0.2}" fill="${shade(legC, -34)}" opacity="0.55"/>
        <ellipse cx="${rSX + legW * 0.07}" cy="${shoeY}" rx="${legW * 0.64}" ry="${h * 0.034}"
                 fill="${shoeC}" stroke="${shade(shoeC, -40)}" stroke-width="${inkW}" stroke-opacity="0.4"/>
        <ellipse cx="${rSX + legW * 0.14}" cy="${shoeY - h * 0.004}" rx="${legW * 0.56}" ry="${h * 0.022}"
                 fill="${shade(shoeC, 30)}"/>
        <ellipse cx="${rSX + legW * 0.24}" cy="${shoeY - h * 0.009}" rx="${legW * 0.26}" ry="${h * 0.008}"
                 fill="${shade(shoeC, 78)}" opacity="0.5"/>
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
            fill="${gSleeve}" stroke="${inkCloth}" stroke-width="${inkW}" stroke-opacity="0.26"/>
      <rect x="${lAX + armW * 0.18}" y="${armTop + armH * 0.04}" width="${armW * 0.28}" height="${armH * 0.62}"
            rx="${armW * 0.1}" fill="${clothHL}" opacity="0.26"/>
      <rect x="${lAX}" y="${armTop + armH * 0.6}" width="${armW}" height="${armW * 0.34}"
            rx="${armW * 0.16}" fill="${clothDk}" opacity="0.3"/>
      <circle cx="${lAX + armW * 0.5}" cy="${armTop + armH + h * 0.006}" r="${armW * 0.5}"
              fill="${gSkin}" stroke="${inkSkin}" stroke-width="${inkW}" stroke-opacity="0.28"/>
      <ellipse cx="${lAX + armW * 0.22}" cy="${armTop + armH + h * 0.002}" rx="${armW * 0.19}" ry="${armW * 0.3}"
               fill="${skinDk}" opacity="0.28"/>
    </g>
    <g transform="rotate(${rArmRot}, ${rShoX}, ${shoY})">
      <rect x="${rAX}" y="${armTop}" width="${armW}" height="${armH}" rx="${armW * 0.48}"
            fill="${gSleeve}" stroke="${inkCloth}" stroke-width="${inkW}" stroke-opacity="0.26"/>
      <rect x="${rAX + armW * 0.18}" y="${armTop + armH * 0.04}" width="${armW * 0.28}" height="${armH * 0.62}"
            rx="${armW * 0.1}" fill="${clothHL}" opacity="0.26"/>
      <rect x="${rAX}" y="${armTop + armH * 0.6}" width="${armW}" height="${armW * 0.34}"
            rx="${armW * 0.16}" fill="${clothDk}" opacity="0.3"/>
      <circle cx="${rAX + armW * 0.5}" cy="${armTop + armH + h * 0.006}" r="${armW * 0.5}"
              fill="${gSkin}" stroke="${inkSkin}" stroke-width="${inkW}" stroke-opacity="0.28"/>
      <ellipse cx="${rAX + armW * 0.78}" cy="${armTop + armH + h * 0.002}" rx="${armW * 0.19}" ry="${armW * 0.3}"
               fill="${skinDk}" opacity="0.28"/>
    </g>
    ${drinkingExtra}
    ${djExtra}`;

  // Body — rounded shoulders + a real neckline. A straight-topped trapezoid
  // (what this used to be) is THE tell of a naive figure: shoulders are the
  // silhouette feature the eye reads first, and square corners make the torso
  // look like a signboard with arms pinned to it.
  const shoulderBroaden = avatar.gender === 'masculine' ? bodyW * 0.05 : 0;
  const hipFlare        = avatar.gender === 'feminine' ? bodyW * 0.12 : 0;
  const shHalf   = bodyW * 0.44 + shoulderBroaden;
  const hipHalf  = bodyW * 0.5 + hipFlare;
  const shR      = bodyW * 0.22;
  const neckHalf = neckW * 0.66;
  const collarY  = bodyTop - bodyH * 0.06;
  // Shared shoulder/neckline cap, reused by the dress so both silhouettes
  // sit on the same anatomy.
  const shoulderCap =
    `M${hcx - shHalf},${bodyTop + shR}` +
    ` C${hcx - shHalf},${bodyTop - shR * 0.42} ${hcx - shHalf * 0.6},${collarY} ${hcx - neckHalf},${collarY}` +
    ` Q${hcx},${collarY + bodyH * 0.075} ${hcx + neckHalf},${collarY}` +
    ` C${hcx + shHalf * 0.6},${collarY} ${hcx + shHalf},${bodyTop - shR * 0.42} ${hcx + shHalf},${bodyTop + shR}`;
  let svgBody = '';
  if (avatar.clothes === 'dress') {
    const spread = bodyW * 0.12;
    const waistY = bodyTop + bodyH * 0.44;
    const waistHalf = shHalf * 0.8;
    const hemHalf = hipHalf + spread;
    const hemY = bodyBot - bodyH * 0.06;
    // A-line: taper to a waist, flare out on a smooth cubic, then close with a
    // curved hem whose corners are ROUNDED. Straight lines into the hem
    // corners produced sharp triangular "wings" wider than the avatar's arms.
    svgBody = `
      <path d="${shoulderCap}
               L${hcx + waistHalf},${waistY}
               C${hcx + waistHalf * 1.06},${waistY + bodyH * 0.16} ${hcx + hemHalf * 0.9},${bodyBot - bodyH * 0.2} ${hcx + hemHalf},${hemY}
               Q${hcx + hemHalf},${bodyBot + bodyH * 0.03} ${hcx + hemHalf * 0.84},${bodyBot + bodyH * 0.045}
               Q${hcx},${bodyBot + bodyH * 0.13} ${hcx - hemHalf * 0.84},${bodyBot + bodyH * 0.045}
               Q${hcx - hemHalf},${bodyBot + bodyH * 0.03} ${hcx - hemHalf},${hemY}
               C${hcx - hemHalf * 0.9},${bodyBot - bodyH * 0.2} ${hcx - waistHalf * 1.06},${waistY + bodyH * 0.16} ${hcx - waistHalf},${waistY}
               L${hcx - shHalf},${bodyTop + shR}Z"
            fill="${gCloth}" stroke="${inkCloth}" stroke-width="${inkW}" stroke-opacity="0.3"
            stroke-linejoin="round"/>
      <path d="M${hcx - waistHalf},${waistY} Q${hcx},${waistY + bodyH * 0.05} ${hcx + waistHalf},${waistY}"
            fill="none" stroke="${clothDk}" stroke-width="${w * 0.028}" opacity="0.4" stroke-linecap="round"/>
      <path d="M${hcx - shHalf * 0.56},${bodyTop + shR * 0.7}
               Q${hcx - waistHalf * 0.9},${waistY} ${hcx - hemHalf * 0.62},${bodyBot}"
            fill="none" stroke="${clothHL}" stroke-width="${w * 0.032}" opacity="0.3" stroke-linecap="round"/>
      <g stroke="${clothDk}" stroke-width="${w * 0.016}" opacity="0.32" fill="none" stroke-linecap="round">
        <path d="M${hcx - waistHalf * 0.45},${waistY + bodyH * 0.04} Q${hcx - hemHalf * 0.4},${bodyBot - bodyH * 0.16} ${hcx - hemHalf * 0.32},${bodyBot + bodyH * 0.03}"/>
        <path d="M${hcx + waistHalf * 0.45},${waistY + bodyH * 0.04} Q${hcx + hemHalf * 0.4},${bodyBot - bodyH * 0.16} ${hcx + hemHalf * 0.32},${bodyBot + bodyH * 0.03}"/>
      </g>`;
  } else {
    svgBody = `
      <path d="${shoulderCap}
               Q${hcx + (shHalf + hipHalf) * 0.5},${bodyTop + bodyH * 0.55} ${hcx + hipHalf},${bodyBot}
               L${hcx - hipHalf},${bodyBot}
               Q${hcx - (shHalf + hipHalf) * 0.5},${bodyTop + bodyH * 0.55} ${hcx - shHalf},${bodyTop + shR}Z"
            fill="${gCloth}" stroke="${inkCloth}" stroke-width="${inkW}" stroke-opacity="0.3"
            stroke-linejoin="round"/>
      <path d="M${hcx - shHalf * 0.56},${bodyTop + shR * 0.7}
               Q${hcx - shHalf * 0.78},${bodyTop + bodyH * 0.56} ${hcx - hipHalf * 0.72},${bodyBot}"
            fill="none" stroke="${clothHL}" stroke-width="${w * 0.032}" opacity="0.3" stroke-linecap="round"/>
      <path d="M${hcx - shHalf * 0.86},${bodyTop + shR * 0.1}
               Q${hcx - shHalf * 0.5},${bodyTop + bodyH * 0.24} ${hcx - shHalf * 0.2},${bodyTop + bodyH * 0.42}"
            fill="none" stroke="${clothDk}" stroke-width="${w * 0.018}" opacity="0.3" stroke-linecap="round"/>
      <path d="M${hcx + shHalf * 0.86},${bodyTop + shR * 0.1}
               Q${hcx + shHalf * 0.5},${bodyTop + bodyH * 0.24} ${hcx + shHalf * 0.2},${bodyTop + bodyH * 0.42}"
            fill="none" stroke="${clothDk}" stroke-width="${w * 0.018}" opacity="0.3" stroke-linecap="round"/>
      <path d="M${hcx - hipHalf * 0.78},${bodyBot}
               Q${hcx},${bodyBot - bodyH * 0.14} ${hcx + hipHalf * 0.78},${bodyBot}"
            fill="none" stroke="${clothDk}" stroke-width="${w * 0.022}" opacity="0.34" stroke-linecap="round"/>`;
  }

  // Shadow cast by the head/jaw onto the chest — the last thing keeping the
  // head from looking like a sticker floating above the shoulders.
  svgBody = `
    <ellipse cx="${hcx}" cy="${collarY + bodyH * 0.02}" rx="${neckHalf * 2.1}" ry="${bodyH * 0.1}"
             fill="rgba(0,0,0,0.16)"/>` + svgBody;

  // Per-clothes decorative details
  let svgClothDetail = '';
  if (avatar.clothes === 'suit') {
    svgClothDetail = `
      <path d="M${hcx - shHalf * 0.68},${collarY + bodyH * 0.02}
               L${hcx},${bodyTop + bodyH * 0.5}
               L${hcx + shHalf * 0.68},${collarY + bodyH * 0.02}
               L${hcx + shHalf * 0.34},${collarY + bodyH * 0.04}
               L${hcx},${bodyTop + bodyH * 0.22}
               L${hcx - shHalf * 0.34},${collarY + bodyH * 0.04}Z"
           fill="${shade(clothC, -52)}"/>
      <path d="M${hcx - shHalf * 0.34},${collarY + bodyH * 0.04}
               L${hcx},${bodyTop + bodyH * 0.46}
               L${hcx + shHalf * 0.34},${collarY + bodyH * 0.04}"
           fill="white" opacity="0.92"/>
      <rect x="${hcx - bodyW * 0.042}" y="${bodyTop + bodyH * 0.06}" width="${bodyW * 0.084}" height="${bodyH * 0.52}"
            rx="${bodyW * 0.02}" fill="#dc2626"/>
      <path d="M${hcx - bodyW * 0.042},${bodyTop + bodyH * 0.06}
               L${hcx},${bodyTop + bodyH * 0.02} L${hcx + bodyW * 0.042},${bodyTop + bodyH * 0.06}Z"
            fill="#b91c1c"/>
      <circle cx="${hcx + bodyW * 0.2}" cy="${bodyTop + bodyH * 0.58}" r="${w * 0.014}" fill="${shade(clothC, 60)}"/>`;
  } else if (avatar.clothes === 'hoodie') {
    svgClothDetail = `
      <path d="M${hcx - neckHalf * 1.5},${collarY}
               Q${hcx},${bodyTop + bodyH * 0.2} ${hcx + neckHalf * 1.5},${collarY}
               Q${hcx},${collarY + bodyH * 0.02} ${hcx - neckHalf * 1.5},${collarY}Z"
            fill="${clothDk}" opacity="0.55"/>
      <g stroke="${shade(clothC, 70)}" stroke-width="${w * 0.018}" stroke-linecap="round" fill="none">
        <path d="M${hcx - neckHalf * 0.7},${bodyTop + bodyH * 0.1} L${hcx - neckHalf * 0.5},${bodyTop + bodyH * 0.3}"/>
        <path d="M${hcx + neckHalf * 0.7},${bodyTop + bodyH * 0.1} L${hcx + neckHalf * 0.5},${bodyTop + bodyH * 0.3}"/>
      </g>
      <rect x="${hcx - bodyW * 0.19}" y="${bodyBot - bodyH * 0.34}" width="${bodyW * 0.38}" height="${bodyH * 0.3}"
            rx="${bodyW * 0.07}" fill="${clothDk}" opacity="0.42"/>
      <path d="M${hcx - bodyW * 0.19},${bodyBot - bodyH * 0.34}
               L${hcx + bodyW * 0.19},${bodyBot - bodyH * 0.34}"
            stroke="${clothDk}" stroke-width="${w * 0.016}" opacity="0.5"/>
      <rect x="${hcx - bodyW * 0.02}" y="${bodyBot - bodyH * 0.04}" width="${bodyW * 0.04}" height="${bodyH * 0.04}"
            fill="${clothDk}" opacity="0.4"/>`;
  } else if (avatar.clothes === 'jacket') {
    svgClothDetail = `
      <path d="M${hcx - neckHalf * 1.4},${collarY + bodyH * 0.01}
               L${hcx - bodyW * 0.09},${bodyTop + bodyH * 0.16}
               L${hcx},${bodyTop + bodyH * 0.08}
               L${hcx + bodyW * 0.09},${bodyTop + bodyH * 0.16}
               L${hcx + neckHalf * 1.4},${collarY + bodyH * 0.01}
               Q${hcx},${collarY + bodyH * 0.06} ${hcx - neckHalf * 1.4},${collarY + bodyH * 0.01}Z"
            fill="${clothDk}"/>
      <line x1="${hcx}" y1="${bodyTop + bodyH * 0.08}" x2="${hcx}" y2="${bodyBot}"
            stroke="${clothDk}" stroke-width="${w * 0.024}"/>
      <line x1="${hcx + w * 0.008}" y1="${bodyTop + bodyH * 0.1}" x2="${hcx + w * 0.008}" y2="${bodyBot}"
            stroke="${clothHL}" stroke-width="${w * 0.008}" opacity="0.5"/>
      <g fill="${clothDk}" opacity="0.55">
        <rect x="${hcx - bodyW * 0.34}" y="${bodyTop + bodyH * 0.52}" width="${bodyW * 0.2}" height="${bodyH * 0.16}" rx="${bodyW * 0.03}"/>
        <rect x="${hcx + bodyW * 0.14}" y="${bodyTop + bodyH * 0.52}" width="${bodyW * 0.2}" height="${bodyH * 0.16}" rx="${bodyW * 0.03}"/>
      </g>`;
  } else if (avatar.clothes === 'tshirt') {
    svgClothDetail = `
      <path d="M${hcx - neckHalf * 1.25},${collarY + bodyH * 0.01}
               Q${hcx},${collarY + bodyH * 0.13} ${hcx + neckHalf * 1.25},${collarY + bodyH * 0.01}"
           fill="none" stroke="${clothDk}" stroke-width="${w * 0.026}" opacity="0.5"
           stroke-linecap="round"/>`;
  }

  // Neck
  const svgNeck = `
    <rect x="${hcx - neckW / 2}" y="${neckTop}" width="${neckW}" height="${neckH + h * 0.018}"
          rx="${neckW * 0.44}" fill="${skin}"/>
    <rect x="${hcx - neckW / 2}" y="${neckTop}" width="${neckW}" height="${neckH * 0.5}"
          rx="${neckW * 0.4}" fill="${skinDk}" opacity="0.38"/>
    <rect x="${hcx - neckW * 0.28}" y="${neckTop}" width="${neckW * 0.26}" height="${neckH}"
          rx="${neckW * 0.13}" fill="${skinLt}" opacity="0.3"/>`;

  // Head — large round chibi head with soft shading
  const svgHead = `
    <ellipse cx="${hcx}" cy="${hcy + hry * 0.045}" rx="${hrx}" ry="${hry}" fill="${skinDk}" opacity="0.2"/>
    <ellipse cx="${hcx - hrx * 0.57}" cy="${hcy}" rx="${hrx * 0.088}" ry="${hry * 0.44}" fill="${skin}"
             stroke="${inkSkin}" stroke-width="${inkW * 0.7}" stroke-opacity="0.3"/>
    <ellipse cx="${hcx + hrx * 0.57}" cy="${hcy}" rx="${hrx * 0.088}" ry="${hry * 0.44}" fill="${skin}"
             stroke="${inkSkin}" stroke-width="${inkW * 0.7}" stroke-opacity="0.3"/>
    <ellipse cx="${hcx}" cy="${hcy}" rx="${hrx}" ry="${hry}" fill="${gSkin}"
             stroke="${inkSkin}" stroke-width="${inkW}" stroke-opacity="0.34"/>
    <ellipse cx="${hcx - hrx * 0.28}" cy="${hcy - hry * 0.12}" rx="${hrx * 0.55}" ry="${hry * 0.45}"
             fill="${skinLt}" opacity="0.2"/>
    <path d="M${hcx - hrx * 0.82},${hcy + hry * 0.42}
             Q${hcx},${hcy + hry * 1.12} ${hcx + hrx * 0.82},${hcy + hry * 0.42}"
          fill="none" stroke="${skinDk}" stroke-width="${w * 0.02}" opacity="0.2"/>`;

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
  const svgBeard   = buildBeard(avatar.beard, w, hcx, hcy, hrx, hry, skin, hairC);
  const svgGlasses = buildGlasses(avatar.glasses, w, hcx, eyeY, eSpr, eRX, eRY);

  // Volumetric gradients: the previous flat single-colour fills gave the
  // figure no sense of roundness. Light is treated as coming from the upper
  // left throughout (matching the rooms' own ceiling fixtures), so the
  // gradients all run light->base->dark on that same diagonal.
  const svgDefs = `
    <defs>
      <radialGradient id="sk-${uid}" cx="36%" cy="30%" r="78%">
        <stop offset="0%"   stop-color="${shade(skin, 34)}"/>
        <stop offset="52%"  stop-color="${skin}"/>
        <stop offset="100%" stop-color="${skinDk}"/>
      </radialGradient>
      <linearGradient id="cl-${uid}" x1="18%" y1="0%" x2="82%" y2="100%">
        <stop offset="0%"   stop-color="${clothHL}"/>
        <stop offset="42%"  stop-color="${clothC}"/>
        <stop offset="100%" stop-color="${clothDk}"/>
      </linearGradient>
      <linearGradient id="sl-${uid}" x1="0%" y1="0%" x2="100%" y2="30%">
        <stop offset="0%"   stop-color="${shade(clothC, 22)}"/>
        <stop offset="60%"  stop-color="${clothC}"/>
        <stop offset="100%" stop-color="${shade(clothC, -30)}"/>
      </linearGradient>
      <linearGradient id="lg-${uid}" x1="0%" y1="0%" x2="100%" y2="20%">
        <stop offset="0%"   stop-color="${shade(legC, 26)}"/>
        <stop offset="58%"  stop-color="${legC}"/>
        <stop offset="100%" stop-color="${shade(legC, -26)}"/>
      </linearGradient>
      <radialGradient id="sh-${uid}" cx="50%" cy="50%" r="50%">
        <stop offset="0%"   stop-color="rgba(0,0,0,0.18)"/>
        <stop offset="60%"  stop-color="rgba(0,0,0,0.10)"/>
        <stop offset="100%" stop-color="rgba(0,0,0,0)"/>
      </radialGradient>
    </defs>`;

  return `<svg class="avatar-svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" overflow="visible" xmlns="http://www.w3.org/2000/svg">
    ${svgDefs}
    ${svgShadow}
    ${accBack}
    ${svgLegs}
    ${svgArms}
    ${svgBody}
    ${svgClothDetail}
    ${svgNeck}
    <g stroke="rgba(255,255,255,0.22)" stroke-width="${w * 0.014}" stroke-linejoin="round">${hBack}</g>
    ${svgHead}
    ${svgEyes}
    ${svgBlush}
    ${svgNose}
    ${svgMouth}
    ${svgBeard}
    ${svgGlasses}
    <g stroke="rgba(255,255,255,0.22)" stroke-width="${w * 0.014}" stroke-linejoin="round">${hFront}</g>
    ${accFront}
  </svg>`;
}
