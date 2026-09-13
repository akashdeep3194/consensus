// A phone dial pad, not ten keys in reading order: 1-2-3 / 4-5-6 / 7-8-9 /
// ·-0-⌫ — the layout everyone already knows from unlocking a phone. Used
// twice with different rules: the slate pad also gets a dedicated clear key
// (there's always a specific "last placed digit" to undo); the vote pad is a
// single pick with nothing to undo, so its outer corners just stay blank —
// kept for the same familiar shape, not for a function.

const ROWS = [[1, 2, 3], [4, 5, 6], [7, 8, 9]];

export function createKeypad(mount, onPick, { onBackspace } = {}) {
  const keys = [];

  function digitKey(digit) {
    const key = document.createElement("button");
    key.type = "button";
    key.className = "key";
    key.textContent = digit;
    key.dataset.digit = digit;
    key.addEventListener("click", () => onPick(digit));
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
    back.setAttribute("aria-label", "clear last digit");
    back.textContent = "⌫";
    back.addEventListener("click", onBackspace);
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
        key.classList.toggle("is-on", digit === selected);
        key.classList.toggle("is-used", spent);
        key.disabled = frozen || spent || full;
      });
      if (keys.backspaceEl) keys.backspaceEl.disabled = frozen || used.length === 0;
    },
  };
}
