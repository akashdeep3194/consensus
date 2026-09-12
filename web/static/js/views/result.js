// The reveal. The one ceremonial surface in the product: a published result,
// set like a printed one rather than another dashboard figure.
import { $, esc } from "../dom.js";

const TIERS = ["TRIFECTA", "BOXED", "TWO", "ONE", "NONE"];

const pct = (share) => `${(share * 100).toFixed(1)}%`;

const stat = (key, value, accent = false) => `
  <div class="stat">
    <div class="label">${esc(key)}</div>
    <div class="stat__v${accent ? " stat__v--accent" : ""}">${esc(value)}</div>
  </div>`;

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

export function createResult() {
  const title = $("resultTitle");
  const body = $("resultBody");

  const tiers = (histogram, mine) => TIERS.map((tier) => {
    const row = histogram.find((x) => x.tier === tier);
    return `<div class="tier${mine?.tier === tier ? " is-mine" : ""}">
      <div class="label">${tier}</div>
      <div class="tier__n">${row ? row.players : 0}</div>
    </div>`;
  }).join("");

  const scorecard = (mine) => !mine ? "" : `
    <div class="scorecard">
      ${stat("Your slate", mine.prediction.split("").join(" "))}
      ${stat("Outcome", mine.tier, true)}
      ${stat("Points", `+${mine.points}`)}
      ${stat("Your vote", `${mine.vote} — finished ${ordinal(mine.vote_finished)}`)}
      ${stat("Slate commanded", pct(mine.vote_share))}
      ${stat("Mandate rank", mine.mandate_rank ? `#${mine.mandate_rank}` : "—")}
    </div>`;

  const mandateBoard = (rows, handle) => !rows.length ? "" : `
    <section class="board">
      <header class="step__head">
        <h3 class="step__title step__title--sm">The Mandate</h3>
        <p class="step__sub">Ranked by position-weighted score
          <span class="formula">3·C[1st] + 2·C[2nd] + 1·C[3rd]</span> — two players whose
          digits drew the same total are separated by getting the order right.</p>
      </header>
      <div class="table-wrap"><table>
        <thead><tr><th>#</th><th>Player</th><th>Slate</th><th>Score</th>
          <th>Commanded</th><th>Outcome</th></tr></thead>
        <tbody>${rows.map((p) => `
          <tr class="${p.handle === handle ? "is-me" : ""}">
            <td>${p.rank}</td>
            <td class="is-name">${esc(p.handle)}</td>
            <td>${esc(p.prediction.split("").join(" "))}</td>
            <td><b>${p.mandate_score}</b></td>
            <td>${pct(p.vote_share)}</td>
            <td>${esc(p.tier)}</td>
          </tr>`).join("")}
        </tbody>
      </table></div>
    </section>`;

  return {
    render(result, mine, { handle, isCurrent }) {
      title.textContent = isCurrent ? "The result" : "Last round";
      body.innerHTML = `
        <div class="reveal">
          <hr class="reveal__rule">
          <div class="reveal__number">${esc(result.winning_number)}</div>
          <hr class="reveal__rule">
          <div class="reveal__caption label">${result.total_votes} votes cast
            · committed as <span class="hash">${esc(result.commitment_root.slice(0, 12))}</span></div>
        </div>
        ${scorecard(mine)}
        <div class="tiers">${tiers(result.tier_histogram, mine)}</div>
        ${mandateBoard(result.mandate_board, handle)}`;
    },
    empty(message) {
      title.textContent = "Result";
      body.innerHTML = `<div class="blind">
        <div class="blind__head">Nothing published yet</div>
        <p class="note note--quiet">${esc(message)}</p></div>`;
    },
  };
}
