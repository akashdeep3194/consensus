// The rules copy is shown twice — the signed-in app's Rules tab, and again
// below the sign-in card so a visitor can read how the game works before
// they ever create a handle. One function, two mount points, so the copy
// itself only ever lives in one place.
export function rulesHTML() {
  return `
    <header class="step__head">
      <h2 class="step__title">Rules &amp; how to play</h2>
      <p class="step__sub">A daily reckoning: predict which three digits the room
        will pick, and cast the one vote that helps decide it.</p>
    </header>

    <div class="rules-copy">
      <h3>How a round works</h3>
      <p>Every round runs for a day. Playing it is two steps:</p>
      <ol>
        <li><b>Make your guess</b> — three distinct digits, ranked 1st, 2nd and
          3rd. This is your prediction of the final order.</li>
        <li><b>Cast your vote</b> — one digit, the one you actually want to win.
          It doesn't have to be on your guess.</li>
      </ol>
      <p>Both are autosaved the moment you pick them, and you can change either
        one freely, right up until the round locks in — at the same instant
        for everyone.</p>

      <h3>How the winning number is decided</h3>
      <p>Everyone's votes are tallied, and the three most-voted digits become the
        winning number — ranked by vote count, so the most-voted digit finishes
        1st, and so on. A tie goes to the lower digit.</p>

      <h3>The room and blackout</h3>
      <p>While a round is open, <span class="term" tabindex="0"
        data-tip="Live vote counts while the round is open — refreshes every few minutes.">The room</span>
        shows the live vote count, so you can see where things stand before
        settling on your own vote. For the last half hour before a round locks
        in, the room goes fully <span class="term" tabindex="0"
        data-tip="No one can see the vote count — but you can still change your guess and vote right up to the end.">dark
        — blackout</span>. You can still change your guess and vote the whole
        time; you just can't see the count while you do.</p>

      <h3>Results</h3>
      <p>Once a round locks in, every entry is committed, the winning number is
        counted, and the <span class="term" tabindex="0"
        data-tip="The winning number and how you did, published once the round locks in and is counted.">result</span>
        is published. Every past round, and how you did in it, lives in History.</p>
    </div>

    <hr class="rules-divider">

    <div class="rules-copy">
      <h3>Scoring — how your guess is judged</h3>
      <div class="table-wrap"><table>
        <thead><tr><th>Outcome</th><th>What it means</th><th>Points</th></tr></thead>
        <tbody>
          <tr><td class="is-name">TRIFECTA</td><td>All three digits, exact order</td><td><b>100</b></td></tr>
          <tr><td class="is-name">BOXED</td><td>All three digits, any order</td><td><b>50</b></td></tr>
          <tr><td class="is-name">TWO</td><td>Exactly two of your three digits</td><td><b>10</b></td></tr>
          <tr><td class="is-name">ONE</td><td>Exactly one of your three digits</td><td><b>2</b></td></tr>
          <tr><td class="is-name">NONE</td><td>None of your digits</td><td><b>0</b></td></tr>
        </tbody>
      </table></div>
      <p class="note note--quiet">Consecutive Trifecta or Boxed rounds build a
        streak, worth up to 3× your points.</p>

      <h3>Worked example</h3>
      <p>Say the votes come in 7 → 40, 2 → 25, 5 → 18, everything else fewer.
        The winning number is <b>725</b> — 7 got the most votes, 2 the next
        most, 5 the third most.</p>
      <ul>
        <li>Guessed <b>725</b>? Exact match, exact order — <b>TRIFECTA</b>, 100 points.</li>
        <li>Guessed <b>572</b>? Same three digits, wrong order — <b>BOXED</b>, 50 points.</li>
        <li>Guessed <b>726</b>? Two of your three (7 and 2) are in it — <b>TWO</b>, 10 points.</li>
        <li>Guessed <b>718</b>? Only one (7) is in it — <b>ONE</b>, 2 points.</li>
        <li>Guessed <b>134</b>? None of them are — <b>NONE</b>, 0 points.</li>
      </ul>

      <h3>The Mandate board</h3>
      <p>A separate <i>rank</i>, not points — it doesn't add to your total.
        Open only to guesses locked in during the first half of the round, it
        ranks those early guesses against each other by
        <code>3×(votes for your 1st) + 2×(votes for your 2nd) + 1×(votes for your 3rd)</code>
        — so in the example above, guessing <b>725</b> outranks guessing
        <b>572</b> here too, even though both land in the same Trifecta/Boxed
        tier for scoring purposes once order stops mattering. Getting the
        order right, and calling it early, is what this board rewards.</p>
    </div>
  `;
}
