/* Playing-card faces as inline SVG.
 *
 * Real pip layouts, not a letter in a box: the arrangement of pips on a 2..10
 * is conventional and instantly readable to anyone who has held a deck, and
 * getting it wrong is the sort of thing that makes a card game feel wrong
 * without the player being able to say why.
 *
 * Layout grid, in fractions of the card face: three pip columns (left, centre,
 * right) and the seven canonical rows. Pips below the midline are drawn
 * upside down, as they are on a real card.
 *
 * Deck note: this game uses 2-7 and 9-A of each suit, the four 8s, and two
 * individually named jokers (RJ red, BJ black) which are askable cards in their
 * own right, so they get real faces rather than a placeholder.
 */
"use strict";

const SUIT = {
  C: { glyph: "♣", red: false },
  D: { glyph: "♦", red: true },
  H: { glyph: "♥", red: true },
  S: { glyph: "♠", red: false },
};

const COL = { L: 0.30, C: 0.5, R: 0.70 };
const ROW = { 1: 0.20, 2.5: 0.315, 3: 0.355, 4: 0.5, 5: 0.645, 5.5: 0.685, 7: 0.80 };

// [column, row] per rank; a row past the midline is drawn inverted.
const PIPS = {
  "2":  [["C", 1], ["C", 7]],
  "3":  [["C", 1], ["C", 4], ["C", 7]],
  "4":  [["L", 1], ["R", 1], ["L", 7], ["R", 7]],
  "5":  [["L", 1], ["R", 1], ["C", 4], ["L", 7], ["R", 7]],
  "6":  [["L", 1], ["R", 1], ["L", 4], ["R", 4], ["L", 7], ["R", 7]],
  "7":  [["L", 1], ["R", 1], ["C", 2.5], ["L", 4], ["R", 4], ["L", 7], ["R", 7]],
  "8":  [["L", 1], ["R", 1], ["C", 2.5], ["L", 4], ["R", 4], ["C", 5.5],
         ["L", 7], ["R", 7]],
  "9":  [["L", 1], ["R", 1], ["L", 3], ["R", 3], ["C", 4], ["L", 5], ["R", 5],
         ["L", 7], ["R", 7]],
  "T":  [["L", 1], ["R", 1], ["C", 2.5], ["L", 3], ["R", 3], ["L", 5], ["R", 5],
         ["C", 5.5], ["L", 7], ["R", 7]],
};

const W = 100, H = 140;                 // face viewBox
const RANK_LABEL = { T: "10" };

function pip(glyph, cx, cy, size, invert) {
  const t = invert ? ` transform="rotate(180 ${cx} ${cy})"` : "";
  return `<text x="${cx}" y="${cy}" font-size="${size}" text-anchor="middle"` +
    ` dominant-baseline="central"${t}>${glyph}</text>`;
}

function corner(label, glyph, x, y, invert) {
  const t = invert ? ` transform="rotate(180 ${x} ${y})"` : "";
  return `<g${t}><text x="${x}" y="${y}" font-size="19" text-anchor="middle"` +
    ` font-weight="600" dominant-baseline="central">${label}</text>` +
    `<text x="${x}" y="${y + 17}" font-size="16" text-anchor="middle"` +
    ` dominant-baseline="central">${glyph}</text></g>`;
}

function courtFace(rank, glyph) {
  return `<rect x="24" y="30" width="52" height="80" rx="5" fill="none"
      stroke="currentColor" stroke-opacity=".35" stroke-width="1.4"/>
    <text x="50" y="63" font-size="34" text-anchor="middle"
      dominant-baseline="central" font-weight="700">${rank}</text>
    <text x="50" y="92" font-size="22" text-anchor="middle"
      dominant-baseline="central">${glyph}</text>`;
}

function jokerFace(red) {
  return `<rect x="22" y="26" width="56" height="88" rx="6" fill="none"
      stroke="currentColor" stroke-opacity=".35" stroke-width="1.4"/>
    <text x="50" y="52" font-size="26" text-anchor="middle"
      dominant-baseline="central">★</text>
    ${["J", "O", "K", "E", "R"].map((ch, i) =>
      `<text x="50" y="${72 + i * 11}" font-size="11" text-anchor="middle"
        letter-spacing="1" dominant-baseline="central" font-weight="600">${ch}</text>`
    ).join("")}
    <text x="50" y="128" font-size="8" text-anchor="middle" opacity=".7"
      dominant-baseline="central">${red ? "RED" : "BLACK"}</text>`;
}

/** Face for a card named like "7C", "TD", "AS", "RJ", "BJ". */
function cardFace(name) {
  const joker = name === "RJ" || name === "BJ";
  const red = joker ? name === "RJ" : SUIT[name.slice(-1)].red;
  const glyph = joker ? "★" : SUIT[name.slice(-1)].glyph;
  const rank = joker ? "" : name.slice(0, -1);
  const label = joker ? (name === "RJ" ? "R" : "B") : (RANK_LABEL[rank] || rank);

  let body;
  if (joker) body = jokerFace(red);
  else if (PIPS[rank]) {
    body = PIPS[rank].map(([c, r]) =>
      pip(glyph, COL[c] * W, ROW[r] * H, rank === "T" || rank === "9" ? 15 : 18,
        ROW[r] > 0.5)).join("");
  } else if (rank === "A") {
    body = pip(glyph, W / 2, H / 2, 44, false);
  } else {
    body = courtFace(rank, glyph);
  }
  return `<svg class="face ${red ? "red" : "blk"}" viewBox="0 0 ${W} ${H}"
      xmlns="http://www.w3.org/2000/svg" aria-label="${name}">
    <rect x="1" y="1" width="${W - 2}" height="${H - 2}" rx="8"
      fill="var(--card-bg)" stroke="var(--card-edge)" stroke-width="1.5"/>
    ${corner(label, glyph, 13, 15, false)}
    ${corner(label, glyph, W - 13, H - 15, true)}
    ${body}
  </svg>`;
}

/** The back of a card, for hands you cannot see. */
function cardBack() {
  return `<svg class="face back" viewBox="0 0 ${W} ${H}"
      xmlns="http://www.w3.org/2000/svg" aria-label="face down">
    <rect x="1" y="1" width="${W - 2}" height="${H - 2}" rx="8"
      fill="var(--back-bg)" stroke="var(--card-edge)" stroke-width="1.5"/>
    <rect x="8" y="8" width="${W - 16}" height="${H - 16}" rx="5"
      fill="none" stroke="var(--back-ink)" stroke-width="1.2" opacity=".8"/>
    <g opacity=".5" fill="var(--back-ink)">
      ${[...Array(6)].map((_, r) => [...Array(4)].map((_, c) =>
        `<circle cx="${18 + c * 21}" cy="${24 + r * 19}" r="2.6"/>`).join("")).join("")}
    </g>
  </svg>`;
}

/**
 * A fanned hand, the way you hold cards.
 *
 * Cards overlap and rotate about a point well below the card, which is what
 * produces the arc in a real hand rather than a row of tiles. The spread is
 * capped so a nine-card hand still fits without the fan folding over itself.
 */
function fan(cards, opts = {}) {
  const n = cards.length;
  if (!n) return `<div class="fan empty">no cards</div>`;
  const spread = Math.min(opts.spread ?? 7, 52 / Math.max(1, n));
  const overlap = opts.overlap ?? Math.min(46, 300 / n);
  return `<div class="fan">` + cards.map((c, i) => {
    const angle = (i - (n - 1) / 2) * spread;
    const sel = opts.selected === c.id ? " sel" : "";
    const dis = opts.enabled === false ? " off" : "";
    return `<div class="slot${sel}${dis}" style="
        transform: rotate(${angle}deg);
        margin-left:${i ? -overlap : 0}px;
        z-index:${i}"
        ${opts.onclick ? `onclick="${opts.onclick}(${c.id})"` : ""}
        title="${c.name}">${cardFace(c.name)}</div>`;
  }).join("") + `</div>`;
}

const RANK_WORD = {
  2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven",
  8: "Eight", 9: "Nine", T: "Ten", J: "Jack", Q: "Queen", K: "King", A: "Ace",
};
const SUIT_WORD = { C: "Clubs", D: "Diamonds", H: "Hearts", S: "Spades" };

/** "7H" -> "Seven of Hearts". Written out because a slow table exists to be
 *  read, and a rank-suit code is something you decode rather than read. */
function prettyCard(name) {
  if (name === "RJ") return "Red Joker";
  if (name === "BJ") return "Black Joker";
  return `${RANK_WORD[name.slice(0, -1)]} of ${SUIT_WORD[name.slice(-1)]}`;
}

/** The suit pip on its own, for inline use in a sentence. */
function glyphOf(name) {
  return (name === "RJ" || name === "BJ") ? "★" : SUIT[name.slice(-1)].glyph;
}

const isRedName = (name) =>
  name === "RJ" ? true : name === "BJ" ? false : SUIT[name.slice(-1)].red;

window.FishCards = { cardFace, cardBack, fan, prettyCard, glyphOf, isRedName };
