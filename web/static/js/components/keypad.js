// A row of ten digit keys. Used twice with different rules: on the slate it
// disables digits already placed, on the vote it marks the one chosen.
// Making a duplicate unpickable is why the slate has no error state.

export function createKeypad(mount, onPick) {
  const keys = [];
  for (let digit = 0; digit <= 9; digit++) {
    const key = document.createElement("button");
    key.type = "button";
    key.className = "key";
    key.textContent = digit;
    key.dataset.digit = digit;
    key.addEventListener("click", () => onPick(digit));
    mount.appendChild(key);
    keys.push(key);
  }

  return {
    render({ selected = null, used = [], frozen = false } = {}) {
      keys.forEach((key, digit) => {
        const spent = used.includes(digit);
        key.classList.toggle("is-on", digit === selected);
        key.classList.toggle("is-used", spent);
        key.disabled = frozen || spent;
      });
    },
  };
}
