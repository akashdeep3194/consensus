// The rules copy is shown twice — the signed-in app's Rules tab, and again
// below the sign-in card so a visitor can read how the game works before
// they ever create a handle. One function, two mount points, so the copy
// itself only ever lives in one place.
export function rulesHTML() {
  return `
    <header class="step__head">
      <h2 class="step__title">Rules &amp; how to play</h2>
      <p class="step__sub">Everyone predicts three digits and votes for one.
        Here's exactly how a round works, step by step.</p>
    </header>

    <div class="rules-copy">
      <h3>How to play</h3>
      <p>A round runs for a full day. Playing it is just two steps:</p>
      <ol>
        <li><b>Make your guess.</b> Pick three different digits and put them
          in order — 1st, 2nd, and 3rd. This is your prediction of the
          winning number.</li>
        <li><b>Cast your vote.</b> Pick one digit — the one you want to win.
          It doesn't have to be one of the three you guessed.</li>
      </ol>
      <p>Both save automatically the moment you pick them, and you can
        change either one as many times as you like — right up until the
        round locks, at the exact same moment for everyone.</p>

      <h3>How the winning number is picked</h3>
      <p>Every vote gets counted. The three digits with the most votes
        become the winning number: the most-voted digit takes 1st place,
        the next takes 2nd, and so on. If two digits are tied, the lower
        digit wins the tie.</p>

      <h3>Watching the room</h3>
      <p>While a round is open, <span class="term" tabindex="0"
        data-tip="Live vote counts while the round is open — refreshes every few minutes.">the room</span>
        shows the live vote count, so you can see how things stand before
        you settle on your vote.</p>

      <h3>Blackout — the last 30 minutes</h3>
      <p>For the final half hour before a round locks, the vote count goes
        dark — that's called <span class="term" tabindex="0"
        data-tip="No one can see the vote count — but you can still change your guess and vote right up to the end.">blackout</span>.
        You can still change your guess and vote right up to the end; you
        just can't see the count while you do.</p>

      <h3>Seeing the result</h3>
      <p>Once a round locks, every entry is final and the votes are
        counted. The <span class="term" tabindex="0"
        data-tip="The winning number and how you did, published once the round locks in and is counted.">result</span>
        — the winning number, and how you did — gets published. Every past
        round lives in your History tab, so you can look back anytime.</p>
    </div>

    <hr class="rules-divider">

    <div class="rules-copy">
      <h3>How your guess earns points</h3>
      <p>Points depend on how closely your guess matches the winning
        number:</p>
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
      <p class="note note--quiet">Land Trifecta or Boxed two rounds in a row
        (or more), and you start earning a streak bonus — up to 3× your
        points.</p>

      <h3>An example</h3>
      <p>Say the winning number turns out to be <b>725</b> — 7 got the most
        votes, 2 the next most, 5 the third most.</p>
      <ul>
        <li>Guessed <b>725</b>? Every digit, in the right place — <b>TRIFECTA</b>, 100 points.</li>
        <li>Guessed <b>572</b>? Same three digits, wrong order — <b>BOXED</b>, 50 points.</li>
        <li>Guessed <b>726</b>? Two of the three (7 and 2) — <b>TWO</b>, 10 points.</li>
        <li>Guessed <b>718</b>? Just one (7) — <b>ONE</b>, 2 points.</li>
        <li>Guessed <b>134</b>? None of them — <b>NONE</b>, 0 points.</li>
      </ul>

      <h3>Bonus: the Mandate board</h3>
      <p>A separate leaderboard — it's a <i>rank</i>, not points, and
        doesn't add to your score. It only includes guesses made in the
        first half of the round, ranked by how many votes their three
        digits drew, weighting 1st place more heavily than 2nd or 3rd.
        That's why, in the example above, guessing <b>725</b> ranks higher
        than guessing <b>572</b> here — even though both are worth the same
        Boxed points once digit order stops mattering for scoring. On this
        board, getting the order right, and guessing early, is what earns
        you a better rank.</p>
      <p class="note note--quiet">The exact formula:
        <code>3×(votes for your 1st) + 2×(votes for your 2nd) + 1×(votes for your 3rd)</code></p>
    </div>
  `;
}
