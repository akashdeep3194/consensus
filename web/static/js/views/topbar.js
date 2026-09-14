// Ambient state only: which round, which phase, how long is left. One
// hairline carries progress across the whole round, with the mandate
// deadline marked to scale — it is the one instant a player can miss.
import { $ } from "../dom.js";
import { now, until, hms } from "../clock.js";

const PHASES = {
  open:      { pill: "Entries open",   tone: "live" },
  blackout:  { pill: "Standings dark", tone: "" },
  sealing:   { pill: "Committing",     tone: "" },
  sealed:    { pill: "Committed",      tone: "" },
  resolving: { pill: "Counting",       tone: "" },
  revealed:  { pill: "Published",      tone: "sage" },
};

const MILESTONES = [
  ["Blackout", "blackout_at"],
  ["Seal",     "seals_at"],
  ["Reveal",   "reveals_at"],
];

const BLACKOUT_TIP = "No one can see the vote count — you can still change "
  + "your guess and vote right up to the end.";

const at = (round, key) => new Date(round[key]).getTime();
const clamp = (n) => Math.min(100, Math.max(0, n));

export function createTopbar() {
  function renderClock(round) {
    const next = MILESTONES.find(([, key]) => until(round[key]) > 0);
    const label = $("cdLabel");
    // Only "Blackout" gets a tooltip here (Room/Result/History already carry
    // their own on the tabs) — swap to innerHTML just for that one label
    // rather than making every tick pay for a term span it won't use.
    if (next && next[0] === "Blackout") {
      label.innerHTML = `<span class="term" tabindex="0" data-tip="${BLACKOUT_TIP}">Blackout</span> in`;
    } else {
      label.textContent = next ? `${next[0]} in` : "Round closed";
    }
    $("countdown").textContent = next ? hms(until(round[next[1]])) : "—";
  }

  /** A second, dedicated countdown to reveals_at specifically — the general
   * clock above only ever shows whichever milestone is soonest, so "how
   * long until the actual result" isn't visible once blackout/seal are
   * the nearer boundary. */
  function renderResultsClock(round) {
    const left = until(round.reveals_at);
    $("resultsCountdown").textContent = left > 0 ? hms(left) : "Published";
  }

  function renderProgress(round) {
    const start = at(round, "opens_at"), end = at(round, "reveals_at");
    const span = end - start;
    $("progressFill").style.width = `${clamp(((now() - start) / span) * 100)}%`;
    const gate = $("progressGate");
    gate.style.left = `${clamp(((at(round, "mandate_deadline") - start) / span) * 100)}%`;
    gate.classList.toggle("is-passed", now() >= at(round, "mandate_deadline"));
  }

  return {
    render(round) {
      if (!round) return;
      const phase = PHASES[round.status] ?? { pill: round.status, tone: "" };
      $("cycle").textContent = String(round.cycle_number).padStart(2, "0");
      const pill = $("phasePill");
      pill.textContent = phase.pill;
      pill.className = `pill${phase.tone ? ` pill--${phase.tone}` : ""}`;
      renderClock(round);
      renderResultsClock(round);
      renderProgress(round);
    },
    tick(round) {
      if (!round) return;
      renderClock(round);
      renderResultsClock(round);
      renderProgress(round);
    },
  };
}
