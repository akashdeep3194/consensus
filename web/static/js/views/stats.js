// The topbar's points chip, and the small popup it opens onto the fuller
// season picture. A season total only changes once a round resolves —
// roughly once a day — so this is fetched once at boot and again
// specifically when the viewer's own round reveals, never polled.
import { $, on, esc, show } from "../dom.js";
import { api } from "../api.js";

const stat = (key, value, accent = false) => `
  <div class="stat">
    <div class="label">${esc(key)}</div>
    <div class="stat__v${accent ? " stat__v--accent" : ""}">${esc(value)}</div>
  </div>`;

const streakText = (n) => (n > 1 ? `${n} in a row` : "—");

export function createStats() {
  const chip = $("myPoints");
  const backdrop = $("statsBackdrop");
  const popup = $("statsPopup");
  let season = null;

  function render() {
    if (!season) return;
    chip.textContent = `${season.total_points} pts`;
    $("statsBody").innerHTML = `
      ${stat("Total points", season.total_points, true)}
      ${stat("Current streak", streakText(season.streak))}
      ${stat("Best streak", streakText(season.best_streak))}
      ${stat("Trifectas", season.trifectas)}
      ${stat("Boxed", season.boxed)}
      ${stat("Rounds played", season.rounds_played)}
      ${stat("Leaderboard rank", season.rank ? `#${season.rank}` : "—")}
    `;
  }

  function open() { show(backdrop, true); show(popup, true); }
  function close() { show(backdrop, false); show(popup, false); }

  on(chip, "click", open);
  on(backdrop, "click", close);
  on($("statsClose"), "click", close);
  on(document, "keydown", (event) => {
    if (event.key === "Escape" && !backdrop.hidden) close();
  });

  return {
    async refresh() {
      season = await api.mySeason();
      render();
    },
  };
}
