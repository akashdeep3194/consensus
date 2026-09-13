// The live tally. The three seated digits are the number if the round sealed
// right now, so they carry the same 1st/2nd/3rd marks the slate slots do.
//
// The count itself only actually changes once every five minutes on the
// server (services.entries.STANDINGS_REFRESH_SECONDS) — the countdown here
// is that real cache expiry, not a decorative timer.
import { $ } from "../dom.js";
import { until, mmss } from "../clock.js";

const SEATS = ["1st", "2nd", "3rd"];

/** Ranked by count descending, ties to the lower digit (§2). */
const seatOrder = (counts) =>
  counts.map((count, digit) => ({ count, digit }))
        .sort((a, b) => b.count - a.count || a.digit - b.digit);

export function createRoom() {
  const body = $("tally");
  const projected = $("projected");
  const refreshLabel = $("standingsRefresh");
  let nextRefreshAt = null;

  function renderCountdown() {
    if (!nextRefreshAt) { refreshLabel.textContent = ""; return; }
    const left = until(nextRefreshAt);
    refreshLabel.textContent = left > 0 ? `Refreshes in ${mmss(left)}` : "Refreshing…";
  }

  return {
    render(standings, myVote) {
      nextRefreshAt = standings?.next_refresh_at ?? null;
      renderCountdown();

      if (!standings?.visible) {
        body.innerHTML = `
          <div class="blind">
            <div class="blind__head">The room has gone dark</div>
            <p class="note note--quiet">Nobody can read the distribution now.
              Whatever you change, you change blind.</p>
          </div>`;
        projected.textContent = "";
        return;
      }

      const ranked = seatOrder(standings.counts);
      const seat = new Map(ranked.slice(0, 3).map((r, i) => [r.digit, SEATS[i]]));
      const max = Math.max(1, ...standings.counts);

      body.innerHTML = standings.counts.map((count, digit) => `
        <div class="tally__row${seat.has(digit) ? " is-seated" : ""}${digit === myVote ? " is-mine" : ""}">
          <div class="tally__seat">${seat.get(digit) ?? ""}</div>
          <div class="tally__digit">${digit}</div>
          <div class="tally__bar"><div class="tally__fill" style="width:${(count / max) * 100}%"></div></div>
          <div class="tally__count">${count}</div>
          <div class="tally__mine" title="your vote"></div>
        </div>`).join("");

      const number = ranked.slice(0, 3).map((r) => r.digit).join("");
      projected.innerHTML = standings.total
        ? `<div class="projected__container">
             <span class="label projected__label">Current Leader</span>
             <div class="projected__number-container">
               <span class="projected__number">${number}</span>
               <span class="projected__votes">${standings.total} vote${standings.total === 1 ? "" : "s"}</span>
             </div>
           </div>`
        : `<div class="projected__container">
             <span class="label projected__label">No Votes Yet</span>
             <div class="projected__number-container">
               <span class="projected__number projected__number--empty">012</span>
               <span class="note note--quiet">Ties resolve low</span>
             </div>
           </div>`;
    },
    tick: renderCountdown,
  };
}
