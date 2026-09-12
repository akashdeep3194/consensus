// The entry, as a short sequence rather than a form: slate, then vote, then
// a receipt. Two steps because "the three you predict" and "the one you vote
// for" are the easiest things in this game to confuse, and each step exists
// to teach one of them.
import { $, on, esc, show } from "../dom.js";
import { until, coarse } from "../clock.js";
import { createKeypad } from "../components/keypad.js";

const ACCEPTING = new Set(["open", "blackout", "sealing"]);
const STEPS = ["slate", "vote", "review", "closed"];

const CLOSED_COPY = {
  sealed:    ["Entries are closed", "The round is sealed. Every entry is committed; the count comes next."],
  resolving: ["Counting", "Votes are being counted now. The number is published at the reveal."],
  revealed:  ["This round is published", "Open the Result tab to see the number and where you landed."],
};

export function createEntry({ onDraftChange, onLock, onGoRoom }) {
  const local = { slate: [null, null, null], vote: null };
  let round = null, entry = null, step = "slate";

  const accepting = () => !!round && ACCEPTING.has(round.status);
  const editable  = () => accepting() && !entry?.locked;
  const complete  = () => local.slate.filter((d) => d !== null).length === 3;

  // ── keypads ─────────────────────────────────────────────────────────────
  const slateKeys = createKeypad($("slateKeys"), (digit) => {
    const next = local.slate.indexOf(null);
    if (next === -1) return;
    local.slate[next] = digit;
    paint();
    emit();
  });

  const voteKeys = createKeypad($("voteKeys"), (digit) => {
    local.vote = digit;
    paint();
    emit();
  });

  const clearSlot = (i) => {
    if (!editable() || local.slate[i] === null) return;
    local.slate[i] = null;
    paint();
    emit();
  };

  $("slots").querySelectorAll(".slot").forEach((node) =>
    on(node, "click", () => clearSlot(Number(node.dataset.pos))));

  on($("toVote"),      "click", () => goto("vote"));
  on($("backToSlate"), "click", () => goto("slate"));
  on($("toReview"),    "click", () => goto("review"));
  on($("edit"),        "click", () => goto("slate"));
  on($("lock"),        "click", () => (entry?.locked ? onGoRoom() : onLock()));

  function goto(next) { step = next; paint(); }

  function emit() {
    onDraftChange({
      prediction: complete() ? local.slate.filter(d => d !== null).join("") : null,
      vote: local.vote,
    });
  }

  /** Digit keys and backspace, forwarded by the router while Play is open. */
  function handleKey(key) {
    if (!editable()) return;
    if (step === "slate") {
      if (/^[0-9]$/.test(key)) $("slateKeys").children[Number(key)].click();
      if (key === "Backspace") {
        const last = local.slate.map((d, i) => [d, i]).filter(([d]) => d !== null).pop()?.[1];
        if (last !== undefined) clearSlot(last);
      }
    } else if (step === "vote" && /^[0-9]$/.test(key)) {
      $("voteKeys").children[Number(key)].click();
    }
  }

  // ── painting ────────────────────────────────────────────────────────────
  function receipt(node) {
    const slate = complete() ? local.slate.filter(d => d !== null).join("  ") : "—";
    node.innerHTML = `
      <div class="receipt__row">
        <span class="label">Slate</span><span class="receipt__v">${esc(slate)}</span>
      </div>
      <div class="receipt__row">
        <span class="label">Vote</span>
        <span class="receipt__v">${local.vote ?? "—"}</span>
      </div>
      ${entry?.locked ? `
      <div class="receipt__row">
        <span class="label">Commit</span>
        <span class="receipt__v receipt__v--quiet">#${entry.commit_sequence}</span>
      </div>` : ""}`;
  }

  function paintReview() {
    receipt($("receipt"));
    const locked = entry?.locked;
    $("reviewTitle").textContent = locked ? "You're in" : "Ready to lock";
    $("reviewSub").textContent = locked
      ? "Committed and counted. Nothing more to do until the reveal."
      : "Nothing is final until you lock in — and you can still change it after.";
    $("lock").textContent = locked ? "Watch the room" : "Lock in";
    show($("edit"), !locked && editable());

    const note = $("mandnote");
    if (locked) {
      note.innerHTML = entry.mandate_eligible
        ? "<b>On the Mandate board.</b> You locked before the deadline, so your slate is also ranked by the weight it commanded."
        : "Locked after the mandate deadline — still live for the Trifecta, but off the Mandate board.";
      return;
    }
    const left = until(round.mandate_deadline);
    note.innerHTML = left > 0
      ? `Lock within <b>${coarse(left)}</b> to also qualify for the Mandate board.`
      : "The mandate deadline has passed — you can still play for the Trifecta.";
  }

  function paintClosed() {
    const [title, sub] = CLOSED_COPY[round.status] ?? ["Entries are closed", ""];
    $("closedTitle").textContent = title;
    $("closedSub").textContent = sub;
    receipt($("closedReceipt"));
    show($("closedReceipt"), complete());
  }

  function paint() {
    STEPS.forEach((name) => show($(`step-${name}`), name === step));

    slateKeys.render({ used: local.slate.filter((d) => d !== null), frozen: !editable() || complete() });
    voteKeys.render({ selected: local.vote, frozen: !editable() });

    local.slate.forEach((digit, i) => {
      const box = $(`slot${i}`);
      box.textContent = digit ?? "–";
      box.classList.toggle("is-empty", digit === null);
    });
    $("slateHint").textContent = complete()
      ? "Tap a slot to clear it."
      : "Tap a digit to place it. Tap a slot to clear it.";

    $("toVote").disabled = !complete();
    $("toReview").disabled = local.vote === null;

    if (step === "review") paintReview();
    if (step === "closed") paintClosed();
  }

  /** Which step a returning player belongs on, given what the server holds. */
  function resume() {
    if (!accepting()) return "closed";
    if (entry?.locked) return "review";
    if (complete() && local.vote !== null) return "review";
    if (complete()) return "vote";
    return "slate";
  }

  return {
    render(nextRound, savedEntry, { force = false } = {}) {
      round = nextRound;
      entry = savedEntry;
      if (force) {
        const slate = entry?.prediction ? entry.prediction.split("").map(Number) : [];
        local.slate = [slate[0] ?? null, slate[1] ?? null, slate[2] ?? null];
        local.vote = entry?.vote ?? null;
        step = resume();
      } else if (step !== "closed" && !accepting()) {
        step = "closed";
      }
      paint();
    },
    markSaved(savedEntry, stamp) {
      entry = savedEntry;
      if (!entry.locked && step === "review") $("status").textContent = `saved ${stamp}`;
    },
    /** Context on the vote step: what the room is doing right now. */
    showLeaders(standings) {
      const node = $("leaders");
      if (!standings?.visible) {
        node.innerHTML = `<span class="label">The room is dark</span>
          <span class="note note--quiet">No one can see the count during blackout.</span>`;
        return;
      }
      const top = standings.counts.map((count, digit) => ({ count, digit }))
        .sort((a, b) => b.count - a.count || a.digit - b.digit)
        .slice(0, 3);
      node.innerHTML = `<span class="label">Leading now</span>
        <span class="leaders__n">${top.map((t) => t.digit).join(" ")}</span>
        <span class="note note--quiet">${standings.total} vote${standings.total === 1 ? "" : "s"} cast</span>`;
    },
    handleKey,
  };
}
