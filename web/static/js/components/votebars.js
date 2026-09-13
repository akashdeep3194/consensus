// One digit-by-digit vote distribution, as ten ranked bars. Shared by two
// call sites that render the exact same shape from different data: the live
// "room" tally (projected, still moving) and a resolved round's histogram
// in History (final, never moving again) — same markup, same seat rule.

const SEATS = ["1st", "2nd", "3rd"];

/** Ranked by count descending, ties to the lower digit — the same tie-break
 * engine/rank.py::winning_number() uses, so these seats equal the actual
 * winning number's digits whenever `counts` is a sealed round's final tally. */
export function renderVoteBars(counts, { myVote = null } = {}) {
  const ranked = counts.map((count, digit) => ({ count, digit }))
                       .sort((a, b) => b.count - a.count || a.digit - b.digit);
  const seat = new Map(ranked.slice(0, 3).map((r, i) => [r.digit, SEATS[i]]));
  const max = Math.max(1, ...counts);

  return counts.map((count, digit) => `
    <div class="tally__row${seat.has(digit) ? " is-seated" : ""}${digit === myVote ? " is-mine" : ""}">
      <div class="tally__seat">${seat.get(digit) ?? ""}</div>
      <div class="tally__digit">${digit}</div>
      <div class="tally__bar"><div class="tally__fill" style="width:${(count / max) * 100}%"></div></div>
      <div class="tally__count">${count}</div>
      <div class="tally__mine" title="your vote"></div>
    </div>`).join("");
}
