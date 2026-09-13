// Browsing past rounds. Past rounds never change, so this fetches lazily on
// first activation rather than on the 4s poll every live view rides — and it
// switches between a list and one round's detail entirely within its own
// subtree, with no callback wiring into main.js (unlike entry.js's onGoRoom).
import { $, esc, on } from "../dom.js";
import { api } from "../api.js";
import { dateTime } from "../clock.js";
import { resultCardHtml } from "../components/resultcard.js";
import { renderVoteBars } from "../components/votebars.js";

/** `getHandle` is a closure, not a value: this view is built once at module
 * scope (like room.js/result.js) but only ever reads it lazily, on a click —
 * long after boot() has actually learned the signed-in handle. */
export function createHistory(getHandle) {
  const title = $("historyTitle");
  const body = $("historyBody");
  const state = { rounds: [], nextBeforeCycle: null, loaded: false };

  function listHtml() {
    if (state.rounds.length === 0) {
      return `<div class="blind">
        <div class="blind__head">No rounds published yet</div>
        <p class="note note--quiet">Check back once the first round is revealed.</p>
      </div>`;
    }
    return `
      <div class="table-wrap"><table>
        <thead><tr><th>Revealed</th><th>Round</th><th>Number</th></tr></thead>
        <tbody>${state.rounds.map((r) => `
          <tr class="history-row" data-round="${r.round_id}" style="cursor:pointer">
            <td>${esc(dateTime(r.reveals_at))}</td>
            <td>#${r.cycle_number}</td>
            <td class="is-name">${esc(r.winning_number)}</td>
          </tr>`).join("")}
        </tbody>
      </table></div>
      <div class="step__foot">
        ${state.nextBeforeCycle != null
          ? `<button class="btn btn--ghost" id="historyMore" type="button">Load more</button>`
          : `<span class="note note--quiet">That's every round so far.</span>`}
      </div>`;
  }

  function renderList() {
    title.textContent = "History";
    body.innerHTML = listHtml();
  }

  async function openDetail(roundId) {
    const round = state.rounds.find((r) => r.round_id === roundId);
    const result = await api.result(roundId);
    let mine = null;
    try { mine = await api.myResult(roundId); } catch { /* didn't enter this round */ }

    title.textContent = round ? dateTime(round.reveals_at) : "Round";
    body.innerHTML = `
      ${resultCardHtml(result, mine, { handle: getHandle() })}
      <section class="board">
        <header class="step__head">
          <h3 class="step__title step__title--sm">Vote distribution</h3>
        </header>
        <div class="tally">${renderVoteBars(result.counts, { myVote: mine?.vote ?? null })}</div>
      </section>
      <div class="step__foot">
        <button class="btn btn--ghost" id="historyBack" type="button">← Back to history</button>
      </div>`;
  }

  async function loadMore() {
    const page = await api.history({ beforeCycle: state.nextBeforeCycle });
    state.rounds = state.rounds.concat(page.rounds);
    state.nextBeforeCycle = page.next_before_cycle;
    renderList();
  }

  on(body, "click", (event) => {
    if (event.target.closest("#historyMore")) { loadMore(); return; }
    if (event.target.closest("#historyBack")) { renderList(); return; }
    const row = event.target.closest(".history-row");
    if (row) openDetail(row.dataset.round);
  });

  return {
    /** Fetches the first page once, the first time History is opened —
     * never again, since past rounds don't change under the viewer. */
    async activate() {
      if (state.loaded) return;
      state.loaded = true;
      const page = await api.history();
      state.rounds = page.rounds;
      state.nextBeforeCycle = page.next_before_cycle;
      renderList();
    },
  };
}
