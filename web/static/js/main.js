// Wiring. Owns the session, the poll loop and the save schedule; the views
// below it never touch the network and the api module never touches the DOM.
import { $, on, esc, show } from "./dom.js";
import { api } from "./api.js";
import { syncTo, clockTime } from "./clock.js";
import { createBand } from "./views/band.js";
import { createEntry } from "./views/entry.js";
import { createStandings } from "./views/standings.js";
import { createResult } from "./views/result.js";

const POLL_MS = 4000;
const TICK_MS = 200;
const SAVE_DEBOUNCE_MS = 450;
const RESOLVED = new Set(["sealed", "resolving", "revealed"]);

const state = { handle: null, round: null, entry: null, draft: null, version: null, shownResult: null };
let saveTimer = null;

const band = createBand();
const standings = createStandings();
const result = createResult();
const entry = createEntry({
  onDraftChange(draft) {
    state.draft = draft;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, SAVE_DEBOUNCE_MS);
  },
  async onLock() {
    clearTimeout(saveTimer);
    await saveDraft();
    try {
      state.entry = await api.lock(state.round.round_id, `${state.round.round_id}:${state.handle}`);
      entry.settle();
      hideError();
      render();
    } catch (err) { showError(err.message); }
  },
});

// ── session ───────────────────────────────────────────────────────────────
on($("signin"), "submit", async (event) => {
  event.preventDefault();
  const handle = $("handle").value.trim();
  if (!handle) return;
  await api.signIn(handle);
  location.reload();
});

on($("advance"), "click", async () => {
  $("advance").disabled = true;
  try { await api.advanceClock(); await refresh(); }
  finally { $("advance").disabled = false; }
});

// ── data ──────────────────────────────────────────────────────────────────
async function saveDraft() {
  if (!state.round || state.entry?.locked || !state.draft) return;
  const { prediction, vote } = state.draft;
  if (prediction === null && vote === null) return;
  try {
    const saved = await api.saveDraft(state.round.round_id, { prediction, vote, version: state.version });
    state.version = saved.version;
    state.entry = saved;
    entry.markSaved(saved, clockTime());
    hideError();
  } catch (err) {
    // A stale version means someone else advanced this entry; re-read rather
    // than clobber.
    if (/version/i.test(err.message)) { entry.settle(); await refresh(); }
    else showError(err.message);
  }
}

async function refresh() {
  try {
    const round = await api.currentRound();
    syncTo(round.server_time);
    const changed = state.round?.round_id !== round.round_id
                 || state.round?.status !== round.status;
    state.round = round;

    state.entry = await api.entry(round.round_id);
    state.version = state.entry?.version ?? null;
    entry.render(round, state.entry, { force: changed });

    standings.render(await api.standings(round.round_id), state.entry?.vote ?? null);
    band.render(round);

    await loadResult(round);
  } catch (err) { showError(err.message); }
}

/** The live round's own result once it exists, otherwise the last published one. */
async function loadResult(round) {
  const current = RESOLVED.has(round.status);
  let roundId = round.round_id;
  if (!current) {
    try { roundId = (await api.latestRevealed()).round_id; }
    catch { result.hide(); return; }
  }
  if (state.shownResult === roundId) return;
  try {
    const published = await api.result(roundId);
    let mine = null;
    try { mine = await api.myResult(roundId); } catch { /* no entry that round */ }
    result.render(published, mine, { handle: state.handle, isCurrent: current });
    state.shownResult = roundId;
  } catch { /* not resolved yet */ }
}

function render() {
  entry.render(state.round, state.entry);
  band.render(state.round);
}

const showError = (message) => { $("err").textContent = message; show($("err"), true); };
const hideError = () => show($("err"), false);

// ── boot ──────────────────────────────────────────────────────────────────
async function boot() {
  const me = await api.me();
  state.handle = me.handle;
  if (!state.handle) { show($("gate"), true); return; }

  show($("gate"), false);
  show($("game"), true);
  $("who").innerHTML = `<span class="who__handle">${esc(state.handle)}</span>
    <button class="btn btn--ghost" id="signout" type="button">Sign out</button>`;
  on($("signout"), "click", async () => { await api.signOut(); location.reload(); });

  await refresh();
  setInterval(refresh, POLL_MS);
  setInterval(() => band.tick(state.round), TICK_MS);
}

boot();
