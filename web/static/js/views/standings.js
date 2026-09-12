// The live tally. The three seated digits are the number if the round
// sealed right now, so they carry the same P₁/P₂/P₃ marks the entry
// slots do — intent on the left, consequence on the right.
import { $ } from "../dom.js";

const SEATS = ["P₁", "P₂", "P₃"];

/** Ranked by count descending, ties to the lower digit (§2). */
const seatOrder = (counts) =>
  counts.map((count, digit) => ({ count, digit }))
        .sort((a, b) => b.count - a.count || a.digit - b.digit);

export function createStandings() {
  const body = $("tally");
  const badge = $("standtag");
  const projected = $("projected");

  return {
    render(standings, myVote) {
      if (!standings || !standings.visible) {
        badge.textContent = "Dark";
        badge.className = "pill";
        body.innerHTML = `
          <div class="blind">
            <div class="blind__head">The room has gone dark</div>
            <p class="note note--quiet">Nobody can read the distribution now.
            Whatever you change, you change blind.</p>
          </div>`;
        projected.textContent = "";
        return;
      }

      badge.textContent = "Live";
      badge.className = "pill pill--live";

      const ranked = seatOrder(standings.counts);
      const seat = new Map(ranked.slice(0, 3).map((r, i) => [r.digit, SEATS[i]]));
      const max = Math.max(1, ...standings.counts);

      body.innerHTML = standings.counts.map((count, digit) => `
        <div class="tally__row${seat.has(digit) ? " is-seated" : ""}${digit === myVote ? " is-mine" : ""}">
          <div class="tally__seat">${seat.get(digit) ?? ""}</div>
          <div class="tally__digit">${digit}</div>
          <div class="tally__bar"><div class="tally__fill" style="width:${(count / max) * 100}%"></div></div>
          <div class="tally__count">${count}</div>
          <div class="tally__mine"></div>
        </div>`).join("");

      const number = ranked.slice(0, 3).map((r) => r.digit).join("");
      projected.innerHTML = standings.total
        ? `<span class="label">Sealed now, the number reads</span>
           <div><span class="projected__number">${number}</span>
           <span class="note note--quiet"> from ${standings.total}
           vote${standings.total === 1 ? "" : "s"}</span></div>`
        : `<span class="label">No votes yet</span>
           <div><span class="projected__number">012</span>
           <span class="note note--quiet"> — with nothing cast, every tie resolves low</span></div>`;
    },
  };
}
