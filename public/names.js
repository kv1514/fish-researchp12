/* Names for the six seats.
 *
 * The table used to read "P0" through "P5", which is what the engine calls the
 * seats internally. That is fine in a log and wrong on a table: a player
 * tracking "did P3 already fail an ask in hearts" is doing bookkeeping the
 * interface should be doing for them, and six identical labels differing by
 * one digit is the hardest possible thing to hold in your head mid-game.
 *
 * So seats get names. Defaults are sea names rather than "Player 1..5" because
 * a name you can say is a name you can remember, and the point is to make the
 * table readable at a glance.
 *
 * Sanitising lives here and is applied on the way IN, so the same rules hold
 * for a name typed in the lobby, a name restored from localStorage and a name
 * arriving from another player over the wire. The server applies its own copy
 * of these limits independently -- this one is for the display, and a
 * client-side check is worth nothing as a boundary.
 */
(function () {
  "use strict";

  /* Five defaults, one per bot seat. Short, distinct first letters, and no two
   * that look alike in a hurry. */
  const BOTS = ["Marlin", "Nori", "Coral", "Reef", "Tide"];

  const MAX = 18;

  /* Characters that render as nothing, or that reorder what follows them.
   *
   * Written as escapes, deliberately. The first version of this held the
   * literal characters, which made this file register as a BINARY FILE to grep
   * and left the most security-relevant regex in the client unreadable in
   * review. A sanitiser nobody can read is not a sanitiser.
   *
   *   0000-001F, 007F  C0 controls and delete
   *   200B-200F        zero-width space/joiner/non-joiner, LTR and RTL marks
   *   202A-202E        bidi embedding and override
   *   2060-2064        word joiner and the invisible operators
   *   FEFF             zero-width no-break space (BOM)
   *
   * These matter because a seat label is read to identify a player. "Ma<ZWSP>rlin"
   * and "Marlin" render identically and compare unequal, so without this a
   * player can sit down at a table as somebody already at it.
   */
  const INVISIBLE = new RegExp(
    "[\\u0000-\\u001F\\u007F"
    + "\\u200B-\\u200F"
    + "\\u202A-\\u202E"
    + "\\u2060-\\u2064"
    + "\\uFEFF]", "g");

  /* Collapse whitespace, strip the invisibles, cap the length. Returns "" for a
   * name that is nothing but spaces, so a caller can fall back to a default
   * rather than render an empty seat.
   *
   * Order matters: stripping precedes the cap. The other way round, a name
   * padded past the cap with zero-width characters would truncate to something
   * shorter than the visible limit, and two different names could cap to the
   * same visible string. */
  function clean(raw) {
    if (raw == null) return "";
    let s = String(raw);
    s = s.replace(INVISIBLE, "");
    s = s.replace(/\s+/g, " ").trim();
    return s.slice(0, MAX);
  }

  /* The name to show for a seat, given whatever the caller has. Never returns
   * empty: an unnamed seat falls back to its default, and a seat past the
   * defaults falls back to a seat label rather than to undefined. */
  function display(names, seat, mySeat, botIndex) {
    const given = clean(names && names[seat]);
    if (given) return given;
    if (seat === mySeat) return "You";
    const i = typeof botIndex === "number" ? botIndex : seat;
    return BOTS[i % BOTS.length] || ("Seat " + seat);
  }

  /* Default names for a solo table: the human's seat takes `me`, the other five
   * take the bot defaults in seat order. Distinct at every seat, which is the
   * property that makes the table readable -- five identical names would be
   * worse than P0..P5. */
  function soloDefaults(mySeat, me) {
    const out = [];
    let b = 0;
    for (let p = 0; p < 6; p++) {
      out.push(p === mySeat ? (clean(me) || "You") : BOTS[b++ % BOTS.length]);
    }
    return out;
  }

  /* Initials for the seat pucks on the felt. Two characters at most: three
   * does not fit and one is ambiguous across six seats. */
  function initials(name) {
    const parts = clean(name).split(" ").filter(Boolean);
    if (!parts.length) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2);
    return parts[0][0] + parts[1][0];
  }

  window.FishNames = { BOTS, MAX, clean, display, soloDefaults, initials };
})();
