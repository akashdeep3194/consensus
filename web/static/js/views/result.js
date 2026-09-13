// The reveal. The one ceremonial surface in the product: a published result,
// set like a printed one rather than another dashboard figure.
import { $, esc } from "../dom.js";
import { resultCardHtml } from "../components/resultcard.js";

export function createResult() {
  const title = $("resultTitle");
  const body = $("resultBody");

  return {
    render(result, mine, { handle, isCurrent }) {
      title.textContent = isCurrent ? "The result" : "Last round";
      body.innerHTML = resultCardHtml(result, mine, { handle });
    },
    empty(message) {
      title.textContent = "Result";
      body.innerHTML = `<div class="blind">
        <div class="blind__head">Nothing published yet</div>
        <p class="note note--quiet">${esc(message)}</p></div>`;
    },
  };
}
