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

  /** Attaches each round's own tier/points, one batched request per page
   * rather than one per row — a round missing from the response is simply
   * one the viewer never entered, rendered as "—", not an error. */
  async function attachMyResults(rounds) {
    if (rounds.length === 0) return;
    const mine = await api.myResults(rounds.map((r) => r.round_id));
    const byRound = new Map(mine.map((m) => [m.round_id, m]));
    for (const r of rounds) {
      const m = byRound.get(r.round_id);
      r.myTier = m?.tier ?? null;
      r.myPoints = m?.points ?? null;
    }
  }

  function errorHtml() {
    return `<div class="blind">
      <div class="blind__head">Couldn't load history</div>
      <p class="note note--quiet">A network hiccup, probably — open the History tab again to retry.</p>
    </div>`;
  }

  function listHtml() {
    if (state.rounds.length === 0) {
      return `<div class="blind">
        <div class="blind__head">No rounds published yet</div>
        <p class="note note--quiet">Check back once the first round is revealed.</p>
      </div>`;
    }
    return `
      <p class="note note--quiet"><span class="term" tabindex="0"
        data-tip="Rounds that got zero votes aren't shown here. There's no result to review from an empty room.">Missing a round?</span></p>
      <div class="table-wrap"><table>
        <thead><tr><th>Revealed</th><th>Round</th><th>Number</th><th>Your result</th></tr></thead>
        <tbody>${state.rounds.map((r) => `
          <tr class="history-row" data-round="${r.round_id}" style="cursor:pointer">
            <td>${esc(dateTime(r.reveals_at))}</td>
            <td>#${r.cycle_number}</td>
            <td class="is-name">${esc(r.winning_number)}</td>
            <td>${r.myTier ? `${esc(r.myTier)} · +${r.myPoints}` : "—"}</td>
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
    await attachMyResults(page.rounds);
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
     * never again, since past rounds don't change under the viewer. `loaded`
     * only flips once that fetch actually succeeds, so a failed attempt
     * (a network blip, a 500) leaves the next tab click free to retry
     * instead of leaving History silently and permanently blank. */
    async activate() {
      if (state.loaded) return;
      try {
        const page = await api.history();
        await attachMyResults(page.rounds);
        state.rounds = page.rounds;
        state.nextBeforeCycle = page.next_before_cycle;
        state.loaded = true;
        renderList();
      } catch {
        title.textContent = "History";
        body.innerHTML = errorHtml();
      }
    },
  };
}
