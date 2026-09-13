// The live tally. The three seated digits are the number if the round sealed
// right now, so they carry the same 1st/2nd/3rd marks the slate slots do.
//
// The count itself only actually changes once every five minutes on the
// server (services.entries.STANDINGS_REFRESH_SECONDS) — the countdown here
// is that real cache expiry, not a decorative timer.
import { $ } from "../dom.js";
import { until, mmss } from "../clock.js";
import { renderVoteBars } from "../components/votebars.js";

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

      body.innerHTML = renderVoteBars(standings.counts, { myVote });

      const ranked = standings.counts.map((count, digit) => ({ count, digit }))
                                      .sort((a, b) => b.count - a.count || a.digit - b.digit);
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
