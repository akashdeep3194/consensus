// Consensus 3D console.
// Server time is authoritative for every phase decision; the local clock is
// only used to interpolate between polls (§6.4).

const $ = (id) => document.getElementById(id);
const api = async (method, path, body) => {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch {}
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
};

const S = {
  handle: null, round: null, entry: null, standings: null,
  prediction: ["", "", ""], vote: null, version: null,
  skew: 0,           // serverTime - clientTime
  saveTimer: null,
};

const PHASES = [
  ["open", "Open"], ["blackout", "Blackout"], ["sealing", "Sealing"],
  ["sealed", "Sealed"], ["resolving", "Resolving"], ["revealed", "Revealed"],
];

const now = () => new Date(Date.now() + S.skew);

// ── boot ──────────────────────────────────────────────────────────────────
async function boot() {
  const me = await api("GET", "/api/me");
  S.handle = me.handle;
  if (!S.handle) { $("gate").hidden = false; return; }
  $("gate").hidden = true;
  $("game").hidden = false;
  buildVotes();
  $("who").innerHTML = `<span>${S.handle}</span>
    <button class="btn btn--ghost" onclick="signOut()">sign out</button>`;
  await refresh();
  setInterval(refresh, 4000);
  setInterval(tick, 200);
}

$("signin").addEventListener("submit", async (e) => {
  e.preventDefault();
  const h = $("handle").value.trim();
  if (!h) return;
  await api("POST", `/api/session?handle=${encodeURIComponent(h)}`);
  location.reload();
});

window.signOut = async () => { await api("DELETE", "/api/session"); location.reload(); };

$("advance").addEventListener("click", async () => {
  $("advance").disabled = true;
  try { await api("POST", "/api/admin/advance"); await refresh(); }
  finally { $("advance").disabled = false; }
});

// ── data ──────────────────────────────────────────────────────────────────
async function refresh() {
  try {
    const r = await api("GET", "/api/rounds/current");
    S.skew = new Date(r.server_time).getTime() - Date.now();
    const changed = !S.round || S.round.round_id !== r.round_id || S.round.status !== r.status;
    S.round = r;

    S.entry = await api("GET", `/api/rounds/${r.round_id}/entry`);
    if (changed || !S.dirty) syncFromEntry();

    S.standings = await api("GET", `/api/rounds/${r.round_id}/standings`);

    render();

    // The current round is live, so the player's last result belongs to an
    // earlier one. Show whichever is available.
    if (["sealed", "resolving", "revealed"].includes(r.status)) {
      loadResult(r.round_id, true);
    } else {
      try {
        const last = await api("GET", "/api/rounds/latest-revealed");
        await loadResult(last.round_id, false);
      } catch { $("resultPanel").hidden = true; }
    }
  } catch (e) { showErr(e.message); }
}

function syncFromEntry() {
  const e = S.entry;
  if (!e) return;
  S.prediction = e.prediction ? e.prediction.split("") : ["", "", ""];
  S.vote = e.vote ?? null;
  S.version = e.version ?? null;
  ["p0", "p1", "p2"].forEach((id, i) => { $(id).value = S.prediction[i] || ""; });
}

// ── entry editing ─────────────────────────────────────────────────────────
["p0", "p1", "p2"].forEach((id, i) => {
  const el = $(id);
  el.addEventListener("input", () => {
    el.value = el.value.replace(/\D/g, "").slice(0, 1);
    S.prediction[i] = el.value;
    if (el.value && i < 2) $(`p${i + 1}`).focus();
    S.dirty = true;
    validate(); scheduleSave();
  });
  el.addEventListener("keydown", (ev) => {
    if (ev.key === "Backspace" && !el.value && i > 0) $(`p${i - 1}`).focus();
  });
});

function buildVotes() {
  const box = $("votes");
  if (box.children.length) return;
  for (let d = 0; d <= 9; d++) {
    const b = document.createElement("button");
    b.className = "vote"; b.textContent = d; b.dataset.d = d;
    b.addEventListener("click", () => {
      if (S.entry?.locked) return;
      S.vote = d; S.dirty = true; renderVotes(); validate(); scheduleSave();
    });
    box.appendChild(b);
  }
}

function validate() {
  const digits = S.prediction.filter((d) => d !== "");
  const complete = digits.length === 3;
  const distinct = new Set(digits).size === digits.length;
  ["p0", "p1", "p2"].forEach((id) => $(id).classList.toggle("bad", complete && !distinct));
  $("predhint").textContent = complete && !distinct
    ? "Digits must be distinct — the winning number never repeats a digit."
    : "The winning number always has three distinct digits.";
  const ok = complete && distinct && S.vote !== null && !S.entry?.locked && isOpenish();
  $("lock").disabled = !ok;
  return complete && distinct;
}

function isOpenish() {
  return S.round && ["open", "blackout", "sealing"].includes(S.round.status);
}

function scheduleSave() {
  clearTimeout(S.saveTimer);
  S.saveTimer = setTimeout(save, 450);
}

async function save() {
  if (!S.round || S.entry?.locked || !isOpenish()) return;
  const digits = S.prediction.filter((d) => d !== "");
  const pred = digits.length === 3 && new Set(digits).size === 3 ? digits.join("") : null;
  if (pred === null && S.vote === null) return;
  try {
    const saved = await api("PUT", `/api/rounds/${S.round.round_id}/draft`, {
      prediction: pred, vote: S.vote, version: S.version,
    });
    S.version = saved.version; S.entry = saved; S.dirty = false;
    hideErr();
    $("saved").textContent = "saved " + new Date().toLocaleTimeString();
  } catch (e) {
    if (/version/i.test(e.message)) { S.dirty = false; await refresh(); }
    else showErr(e.message);
  }
}

$("lock").addEventListener("click", async () => {
  clearTimeout(S.saveTimer);
  await save();
  try {
    S.entry = await api("POST", `/api/rounds/${S.round.round_id}/lock`, {
      idempotency_key: `${S.round.round_id}:${S.handle}`,
    });
    S.dirty = false; hideErr(); render();
  } catch (e) { showErr(e.message); }
});

// ── render ────────────────────────────────────────────────────────────────
function render() {
  const r = S.round;
  if (!r) {
    $("phase").textContent = "No live round";
    $("countdown").textContent = "—";
    return;
  }

  $("cycle").textContent = "#" + r.cycle_number;
  $("phase").textContent = (PHASES.find(([k]) => k === r.status) || [, r.status])[1];
  renderTrack(); renderVotes(); renderStandings(); validate();

  const locked = S.entry?.locked;
  ["p0", "p1", "p2"].forEach((id) => { $(id).disabled = locked || !isOpenish(); });
  $("lock").textContent = locked ? "Locked in ✓" : "Lock in";

  if (locked) {
    $("saved").textContent = `sequence #${S.entry.commit_sequence}`;
    $("mandnote").innerHTML = S.entry.mandate_eligible
      ? `<b>Mandate eligible</b> — locked before the deadline, so you're on Board B.`
      : `Locked after the mandate deadline — Trifecta only, not on Board B.`;
  } else if (isOpenish()) {
    const left = new Date(r.mandate_deadline) - now();
    $("mandnote").innerHTML = left > 0
      ? `Lock within <b>${dur(left)}</b> to qualify for the Mandate board.`
      : `Mandate deadline passed — you can still play for the Trifecta.`;
  } else $("mandnote").textContent = "";
}

function renderTrack() {
  const r = S.round, t = $("track");
  const marks = [
    ["Open", r.opens_at], ["Blackout", r.blackout_at],
    ["Seal", r.seals_at], ["Reveal", r.reveals_at],
  ];
  if (t.children.length !== 3) {
    t.innerHTML = "";
    for (let i = 0; i < 3; i++) {
      const d = document.createElement("div");
      d.className = "seg";
      d.innerHTML = `<div class="rail"><i></i></div><span>${marks[i][0]}</span>`;
      t.appendChild(d);
    }
  }
  const n = now().getTime();
  for (let i = 0; i < 3; i++) {
    const a = new Date(marks[i][1]).getTime(), b = new Date(marks[i + 1][1]).getTime();
    const seg = t.children[i];
    const done = n >= b, active = n >= a && n < b;
    seg.classList.toggle("done", done);
    seg.classList.toggle("now", active);
    const pct = done ? 100 : active ? ((n - a) / (b - a)) * 100 : 0;
    seg.querySelector("i").style.width = pct + "%";
  }
}

function renderVotes() {
  [...$("votes").children].forEach((b) => {
    b.classList.toggle("on", Number(b.dataset.d) === S.vote);
    b.disabled = S.entry?.locked || !isOpenish();
  });
}

function renderStandings() {
  const s = S.standings, box = $("stand"), tag = $("standtag");
  if (!s || !s.visible) {
    tag.textContent = "DARK"; tag.className = "tag dim";
    box.innerHTML = `<div class="dark"><div class="big">Standings are hidden</div>
      Nobody can see the distribution now. Play blind.</div>`;
    $("projected").textContent = "";
    return;
  }
  tag.textContent = "LIVE"; tag.className = "tag";
  const max = Math.max(1, ...s.counts);
  const ranked = s.counts.map((c, d) => [c, d])
    .sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  const top3 = ranked.slice(0, 3).map(([, d]) => d);

  box.innerHTML = s.counts.map((c, d) => `
    <div class="bar ${top3.includes(d) ? "lead" : ""} ${d === S.vote ? "mine" : ""}">
      <div class="d">${d}</div>
      <div class="t"><div class="f" style="width:${(c / max) * 100}%"></div></div>
      <div class="n">${c}</div>
    </div>`).join("");

  $("projected").innerHTML = s.total
    ? `If sealed now, the number would be <b>${top3.join("")}</b>
       <span style="color:var(--muted)"> · ${s.total} vote${s.total === 1 ? "" : "s"} cast</span>`
    : `<span style="color:var(--muted)">No votes yet. With none at all, ties resolve low and
       the number is <b style="font-size:15px">012</b>.</span>`;
}

// ── result ────────────────────────────────────────────────────────────────
async function loadResult(roundId, isCurrent) {
  if (S.shownResult === roundId) return;
  try {
    const r = await api("GET", `/api/rounds/${roundId}/result`);
    let mine = null;
    try { mine = await api("GET", `/api/rounds/${roundId}/my-result`); } catch {}

    const tiers = ["TRIFECTA", "BOXED", "TWO", "ONE", "NONE"].map((t) => {
      const hit = r.tier_histogram.find((x) => x.tier === t);
      return `<div class="tierbox ${mine && mine.tier === t ? "hit" : ""}">
        <div class="k">${t}</div><div class="v">${hit ? hit.players : 0}</div></div>`;
    }).join("");

    const mineCard = mine ? `
      <div class="mine-card">
        <div class="grid">
          <div><div class="k">YOUR PREDICTION</div><div class="v">${mine.prediction}</div></div>
          <div><div class="k">RESULT</div><div class="v big">${mine.tier}</div></div>
          <div><div class="k">POINTS</div><div class="v">+${mine.points}</div></div>
          <div><div class="k">YOUR VOTE</div><div class="v">${mine.vote} → finished #${mine.vote_finished}</div></div>
          <div><div class="k">SLATE COMMANDED</div><div class="v">${(mine.vote_share * 100).toFixed(1)}%</div></div>
          <div><div class="k">MANDATE RANK</div><div class="v">${mine.mandate_rank ? "#" + mine.mandate_rank : "—"}</div></div>
        </div>
      </div>` : "";

    const board = r.mandate_board.length ? `
      <h2 style="margin-top:6px">Mandate board</h2>
      <div class="boardnote">Ranked by position-weighted score
        <span class="mono">3·C[P₁] + 2·C[P₂] + 1·C[P₃]</span> — so two players whose digits
        drew the same total are separated by getting the order right.</div>
      <table><thead><tr><th>#</th><th>Player</th><th>Slate</th><th>Score</th>
        <th>Commanded</th><th>Tier</th></tr></thead>
      <tbody>${r.mandate_board.map((p) => `
        <tr class="${p.handle === S.handle ? "me" : ""}">
          <td>${p.rank}</td><td class="h">${p.handle}</td><td>${p.prediction}</td>
          <td><b>${p.mandate_score}</b></td>
          <td>${(p.vote_share * 100).toFixed(1)}%</td><td>${p.tier}</td></tr>`).join("")}
      </tbody></table>` : "";

    $("resultPanel").querySelector("h2").textContent =
      isCurrent ? "Result" : "Last round's result";
    $("resultBody").innerHTML = `
      <div class="win">${r.winning_number}</div>
      <div class="wl">winning number · ${r.total_votes} votes · root ${r.commitment_root.slice(0, 12)}…</div>
      ${mineCard}<div class="tiers">${tiers}</div>${board}`;
    $("resultPanel").hidden = false;
    S.shownResult = roundId;
  } catch { /* not resolved yet */ }
}

// ── clock ─────────────────────────────────────────────────────────────────
function tick() {
  if (!S.round) return;
  const r = S.round;
  const next = [["blackout", r.blackout_at], ["seal", r.seals_at], ["reveal", r.reveals_at]]
    .find(([, t]) => new Date(t) > now());
  if (!next) { $("cd-label").textContent = "Revealed"; $("countdown").textContent = "—"; return; }
  $("cd-label").textContent = `${next[0]} in`;
  $("countdown").textContent = dur(new Date(next[1]) - now());
  renderTrack();
}

function dur(ms) {
  if (ms < 0) ms = 0;
  const s = Math.floor(ms / 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor(s / 60) % 60)}:${p(s % 60)}`;
}

const showErr = (m) => { $("err").textContent = m; $("err").hidden = false; };
const hideErr = () => { $("err").hidden = true; };

boot();
