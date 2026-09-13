// The entry, as a short sequence rather than a form: slate, then vote, then
// a standing summary. Two picking steps because "the three you predict" and
// "the one you vote for" are the easiest things in this game to confuse, and
// each step exists to teach one of them.
//
// There is no lock-in step. A draft is autosaved on every change and stays
// editable for as long as the round accepts entries — right up to the same
// instant for everyone — so the "review" step is just a steady summary of
// what's currently saved, not a decision to make.
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

export function createEntry({ onDraftChange, onGoRoom }) {
  const local = { slate: [null, null, null], vote: null };
  let round = null, entry = null, step = "slate";

  const accepting = () => !!round && ACCEPTING.has(round.status);
  // Once the round has committed this entry — normally only once it has
  // closed, but see the race note on paintClosed() below — nothing here is
  // editable any more, whatever the round's own status still says.
  const editable  = () => accepting() && !entry?.committed;
  const placed    = () => local.slate.filter((d) => d !== null);
  const complete  = () => placed().length === 3;

  // ── keypads ─────────────────────────────────────────────────────────────
  const slateKeys = createKeypad($("slateKeys"), (digit) => {
    const next = local.slate.indexOf(null);   // fills the first gap, wherever it is
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
    // Clear only the box that was tapped. Collapsing left would move digits
    // the player never touched: clearing 1st would promote their 2nd pick to
    // first place, which is the opposite of what tapping it asks for.
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
  on($("viewRoom"),    "click", () => onGoRoom());

  function goto(next) { step = next; paint(); }

  function emit() {
    onDraftChange({
      prediction: complete() ? placed().join("") : null,
      vote: local.vote,
    });
  }

  /** Digit keys and backspace, forwarded by the router while Play is open. */
  function handleKey(key) {
    if (!editable()) return;
    if (step === "slate") {
      if (/^[0-9]$/.test(key)) $("slateKeys").children[Number(key)].click();
      if (key === "Backspace") {
        const last = placed().length - 1;
        if (last >= 0) clearSlot(last);
      }
    } else if (step === "vote" && /^[0-9]$/.test(key)) {
      $("voteKeys").children[Number(key)].click();
    }
  }

  // ── painting ────────────────────────────────────────────────────────────
  function receipt(node) {
    const slate = complete() ? placed().join("  ") : "—";
    node.innerHTML = `
      <div class="receipt__row">
        <span class="label">Slate</span><span class="receipt__v">${esc(slate)}</span>
      </div>
      <div class="receipt__row">
        <span class="label">Vote</span>
        <span class="receipt__v">${local.vote ?? "—"}</span>
      </div>
      ${entry?.committed ? `
      <div class="receipt__row">
        <span class="label">Commit</span>
        <span class="receipt__v receipt__v--quiet">#${entry.commit_sequence}</span>
      </div>
      <div class="receipt__row">
        <span class="label">Mandate</span>
        <span class="receipt__v receipt__v--quiet">${entry.mandate_eligible ? "Eligible" : "Not eligible"}</span>
      </div>` : ""}`;
  }

  /** True once the draft last saved to the server would score the Mandate
   * board — i.e. it was last written before the deadline. Mirrors the same
   * comparison the sealing worker makes with `draft.updated_at` (ruleset
   * §3.2); the client only ever sees its own reflection of that timestamp. */
  function mandateEligibleNow() {
    if (!entry?.updated_at) return false;
    return new Date(entry.updated_at) < new Date(round.mandate_deadline);
  }

  function paintReview() {
    receipt($("receipt"));
    $("reviewTitle").textContent = "Your entry";
    $("reviewSub").textContent = "Autosaved. Edit it freely until entries close.";
    show($("edit"), editable());

    const eligible = mandateEligibleNow();
    const left = until(round.mandate_deadline);
    const note = $("mandnote");
    if (eligible) {
      note.innerHTML = left > 0
        ? `<b>On the Mandate board</b> as it stands — stays true as long as you leave it alone for the next <b>${coarse(left)}</b>.`
        : `<b>On the Mandate board.</b> Settled before the deadline and unchanged since.`;
    } else {
      note.innerHTML = left > 0
        ? `Not on the Mandate board yet — you've edited since the last check. Leave it as-is for <b>${coarse(left)}</b> and it will be.`
        : `Off the Mandate board — this was last changed after the deadline. Still fully live for the Trifecta.`;
    }
  }

  function paintClosed() {
    // A player can land here two ways: the round genuinely closed, or (much
    // rarer) their draft was already swept into a commit mid-seal while the
    // round's own status still nominally accepts entries. Both are
    // permanent from here, but only one is "the round is over."
    const stillAccepting = accepting() && entry?.committed;
    const [title, sub] = stillAccepting
      ? ["You're in", "This entry has been committed and can no longer be changed."]
      : (CLOSED_COPY[round.status] ?? ["Entries are closed", ""]);
    $("closedTitle").textContent = title;
    $("closedSub").textContent = sub;
    receipt($("closedReceipt"));
    show($("closedReceipt"), complete() || entry?.committed);
  }

  function paint() {
    STEPS.forEach((name) => show($(`step-${name}`), name === step));

    slateKeys.render({ used: placed(), frozen: !editable() || complete() });
    voteKeys.render({ selected: local.vote, frozen: !editable() });

    local.slate.forEach((digit, i) => {
      const box = $(`slot${i}`);
      box.textContent = digit ?? "–";
      box.classList.toggle("is-empty", digit === null);
    });
    $("slateHint").textContent = complete()
      ? "Tap a slot to clear it and re-rank."
      : "Tap a digit to place it. Tap a slot to clear it.";

    $("toVote").disabled = !complete();
    $("toReview").disabled = local.vote === null;

    if (step === "review") paintReview();
    if (step === "closed") paintClosed();
  }

  /** Which step a returning player belongs on, given what the server holds. */
  function resume() {
    if (!accepting() || entry?.committed) return "closed";
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
      } else if (step !== "closed" && (!accepting() || entry?.committed)) {
        step = "closed";
      }
      paint();
    },
    markSaved(savedEntry, stamp) {
      entry = savedEntry;
      if (!entry.committed && step === "review") $("status").textContent = `saved ${stamp}`;
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
