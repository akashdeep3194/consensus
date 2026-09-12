// The phase band: which round, which phase, how long it lasts.
import { $, esc } from "../dom.js";
import { now, until, hms } from "../clock.js";

// Phase presentation as data, mirroring the way the server keeps its
// transition table: adding a phase means adding a row, not a branch.
const PHASES = {
  open:      { name: "Open",      pill: "Entries open",   tone: "live" },
  blackout:  { name: "Blackout",  pill: "Standings dark", tone: "" },
  sealing:   { name: "Sealing",   pill: "Committing",     tone: "" },
  sealed:    { name: "Sealed",    pill: "Committed",      tone: "" },
  resolving: { name: "Resolving", pill: "Counting",       tone: "" },
  revealed:  { name: "Revealed",  pill: "Published",      tone: "sage" },
};

const SEGMENTS = [
  { label: "Open",     from: "opens_at",    to: "blackout_at" },
  { label: "Blackout", from: "blackout_at", to: "seals_at" },
  { label: "Sealed",   from: "seals_at",    to: "reveals_at" },
];

const MILESTONES = [
  ["Blackout", "blackout_at"],
  ["Seal",     "seals_at"],
  ["Reveal",   "reveals_at"],
];

const at = (round, key) => new Date(round[key]).getTime();

export function createBand() {
  const track = $("track");

  function buildTrack() {
    if (track.children.length === SEGMENTS.length) return;
    track.innerHTML = SEGMENTS.map((s, i) => `
      <div class="seg">
        <div class="seg__rail">
          <i class="seg__fill"></i>
          ${i === 0 ? '<span class="seg__gate" title="Mandate deadline"></span>' : ""}
        </div>
        <div class="seg__label">${esc(s.label)}</div>
      </div>`).join("");
  }

  function renderTrack(round) {
    buildTrack();
    const t = now();
    SEGMENTS.forEach((seg, i) => {
      const node = track.children[i];
      const start = at(round, seg.from), end = at(round, seg.to);
      const done = t >= end, active = t >= start && t < end;
      node.classList.toggle("is-done", done);
      node.classList.toggle("is-now", active);
      const pct = done ? 100 : active ? ((t - start) / (end - start)) * 100 : 0;
      node.querySelector(".seg__fill").style.width = `${pct}%`;

      // The mandate deadline is placed to scale inside the open window —
      // it is the one instant a player can miss by being slow.
      const gate = node.querySelector(".seg__gate");
      if (gate) {
        const gateAt = at(round, "mandate_deadline");
        gate.style.left = `${((gateAt - start) / (end - start)) * 100}%`;
        node.classList.toggle("is-gate-passed", t >= gateAt);
      }
    });
  }

  /** Counts down to the next milestone; called every frame-ish tick. */
  function renderClock(round) {
    const next = MILESTONES.find(([, key]) => until(round[key]) > 0);
    if (!next) {
      $("cdLabel").textContent = "Round closed";
      $("countdown").textContent = "—";
      return;
    }
    $("cdLabel").textContent = `${next[0]} in`;
    $("countdown").textContent = hms(until(round[next[1]]));
  }

  return {
    render(round) {
      if (!round) {
        $("phase").textContent = "No live round";
        $("countdown").textContent = "—";
        return;
      }
      const phase = PHASES[round.status] ?? { name: round.status, pill: "", tone: "" };
      $("cycle").textContent = String(round.cycle_number).padStart(2, "0");
      $("phase").textContent = phase.name;
      const pill = $("phasePill");
      pill.textContent = phase.pill;
      pill.className = `pill${phase.tone ? ` pill--${phase.tone}` : ""}`;
      renderTrack(round);
      renderClock(round);
    },
    tick(round) {
      if (!round) return;
      renderClock(round);
      renderTrack(round);
    },
  };
}
