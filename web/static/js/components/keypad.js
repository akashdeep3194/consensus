// A phone dial pad, not ten keys in reading order: 1-2-3 / 4-5-6 / 7-8-9 /
// ·-0-⌫ — the layout everyone already knows from unlocking a phone. Used
// twice with different rules: the slate pad also gets a dedicated clear key
// (there's always a specific "last placed digit" to undo); the vote pad is a
// single pick with nothing to undo, so its outer corners just stay blank —
// kept for the same familiar shape, not for a function.
//
// Disabled state is tracked as a class + a flag the click handler itself
// checks, never the native `disabled` attribute. Every digit placement
// re-renders every key's disabled state, and mutating `disabled` on a button
// while a touch is still resolving (touchstart -> touchend -> click) is a
// known way for mobile browsers to silently drop that click entirely — the
// exact "placed one digit, next tap does nothing" failure this pad cannot
// afford. Blocking inside the handler sidesteps that risk completely.

const ROWS = [[1, 2, 3], [4, 5, 6], [7, 8, 9]];

export function createKeypad(mount, onPick, { onBackspace } = {}) {
  const keys = [];

  function digitKey(digit) {
    const key = document.createElement("button");
    key.type = "button";
    key.className = "key";
    key.textContent = digit;
    key.dataset.digit = digit;
    key.dataset.blocked = "false";
    key.addEventListener("click", () => {
      if (key.dataset.blocked === "true") return;
      onPick(digit);
    });
    mount.appendChild(key);
    keys[digit] = key;
  }

  function spacer() {
    const s = document.createElement("span");
    s.className = "key key--spacer";
    s.setAttribute("aria-hidden", "true");
    mount.appendChild(s);
  }

  for (const row of ROWS) for (const digit of row) digitKey(digit);

  spacer();
  digitKey(0);
  if (onBackspace) {
    const back = document.createElement("button");
    back.type = "button";
    back.className = "key key--back";
    back.dataset.blocked = "false";
    back.setAttribute("aria-label", "clear last digit");
    back.textContent = "⌫";
    back.addEventListener("click", () => {
      if (back.dataset.blocked === "true") return;
      onBackspace();
    });
    mount.appendChild(back);
    keys.backspaceEl = back;
  } else {
    spacer();
  }

  return {
    /** `frozen` disables the whole pad, ⌫ included (nothing is editable at
     * all). `full` only stops new digits (nowhere left to put one) — ⌫ stays
     * live, since clearing one to make room is exactly the point of it. */
    render({ selected = null, used = [], frozen = false, full = false } = {}) {
      keys.forEach((key, digit) => {
        const spent = used.includes(digit);
        const blocked = frozen || spent || full;
        key.classList.toggle("is-on", digit === selected);
        key.classList.toggle("is-used", spent);
        key.classList.toggle("is-blocked", blocked);
        key.dataset.blocked = String(blocked);
        key.setAttribute("aria-disabled", String(blocked));
      });
      if (keys.backspaceEl) {
        const blocked = frozen || used.length === 0;
        keys.backspaceEl.classList.toggle("is-blocked", blocked);
        keys.backspaceEl.dataset.blocked = String(blocked);
        keys.backspaceEl.setAttribute("aria-disabled", String(blocked));
      }
    },
  };
}
