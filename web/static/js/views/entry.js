// The entry panel: a ranked slate of three digits, plus the one vote that
// shapes the outcome. Owns its input state; reports intent upward.
import { $, on, setClass } from "../dom.js";
import { until, coarse } from "../clock.js";

const SLOT_IDS = ["p0", "p1", "p2"];
const EDITABLE_PHASES = new Set(["open", "blackout", "sealing"]);

const HINT = {
  ok:   "Order counts. P₁ is the digit you back to finish first.",
  dupe: "Digits must be distinct — the winning number never repeats one.",
};

export function createEntry({ onDraftChange, onLock }) {
  const local = { prediction: ["", "", ""], vote: null, dirty: false };
  let round = null, entry = null;

  const editable = () =>
    !!round && EDITABLE_PHASES.has(round.status) && !entry?.locked;

  const digits = () => local.prediction.filter((d) => d !== "");
  const complete = () => digits().length === 3;
  const distinct = () => new Set(digits()).size === digits().length;

  // ── keypad ──────────────────────────────────────────────────────────────
  const keypad = $("keypad");
  for (let d = 0; d <= 9; d++) {
    const key = document.createElement("button");
    key.type = "button";
    key.className = "key";
    key.textContent = d;
    key.dataset.digit = d;
    key.setAttribute("aria-label", `vote for ${d}`);
    on(key, "click", () => {
      if (!editable()) return;
      local.vote = d;
      local.dirty = true;
      paint();
      emit();
    });
    keypad.appendChild(key);
  }

  // ── slots ───────────────────────────────────────────────────────────────
  SLOT_IDS.forEach((id, i) => {
    const el = $(id);
    on(el, "input", () => {
      el.value = el.value.replace(/\D/g, "").slice(0, 1);
      local.prediction[i] = el.value;
      if (el.value && i < 2) $(SLOT_IDS[i + 1]).focus();
      local.dirty = true;
      paint();
      emit();
    });
    on(el, "keydown", (ev) => {
      if (ev.key === "Backspace" && !el.value && i > 0) $(SLOT_IDS[i - 1]).focus();
    });
  });

  on($("lock"), "click", () => onLock());

  function emit() {
    const slate = complete() && distinct() ? digits().join("") : null;
    onDraftChange({ prediction: slate, vote: local.vote });
  }

  /** Everything that depends only on local input state. */
  function paint() {
    const bad = complete() && !distinct();
    SLOT_IDS.forEach((id) => setClass($(id), "is-bad", bad));
    $("predhint").textContent = bad ? HINT.dupe : HINT.ok;

    const open = editable();
    SLOT_IDS.forEach((id) => { $(id).disabled = !open; });
    [...keypad.children].forEach((key) => {
      setClass(key, "is-on", Number(key.dataset.digit) === local.vote);
      key.disabled = !open;
    });
    $("lock").disabled = !(open && complete() && distinct() && local.vote !== null);
  }

  function renderMandateNote() {
    const note = $("mandnote");
    if (entry?.locked) {
      note.innerHTML = entry.mandate_eligible
        ? "<b>On the Mandate board.</b> Locked before the deadline, so your slate is ranked by the weight it commanded."
        : "Locked after the mandate deadline — still live for the Trifecta, but off the Mandate board.";
      return;
    }
    if (!editable()) { note.textContent = ""; return; }
    const left = until(round.mandate_deadline);
    note.innerHTML = left > 0
      ? `Lock within <b>${coarse(left)}</b> to qualify for the Mandate board.`
      : "Mandate deadline passed — you can still play for the Trifecta.";
  }

  return {
    /** Adopt server state unless the player is mid-edit. */
    render(next, savedEntry, { force = false } = {}) {
      round = next;
      entry = savedEntry;
      if (entry && (force || !local.dirty)) {
        local.prediction = entry.prediction ? entry.prediction.split("") : ["", "", ""];
        local.vote = entry.vote ?? null;
        SLOT_IDS.forEach((id, i) => { $(id).value = local.prediction[i] || ""; });
      }
      $("lock").textContent = entry?.locked ? "Locked in" : "Lock in";
      $("status").textContent = entry?.locked ? `commit #${entry.commit_sequence}` : "";
      paint();
      renderMandateNote();
    },
    markSaved(savedEntry, stamp) {
      entry = savedEntry;
      local.dirty = false;
      if (!entry.locked) $("status").textContent = `saved ${stamp}`;
    },
    settle() { local.dirty = false; },
  };
}
