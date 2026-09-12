// Wiring. Owns the session, the poll loop, the save schedule and which of the
// three views is on screen. The views below never touch the network, and the
// api module never touches the DOM.
import { $, on, esc, show } from "./dom.js";
import { api } from "./api.js";
import { syncTo, clockTime } from "./clock.js";
import { createTopbar } from "./views/topbar.js";
import { createEntry } from "./views/entry.js";
import { createRoom } from "./views/room.js";
import { createResult } from "./views/result.js";

const POLL_MS = 4000;
const TICK_MS = 200;
const SAVE_DEBOUNCE_MS = 450;
const VIEWS = ["play", "room", "result"];
const RESOLVED = new Set(["sealed", "resolving", "revealed"]);

const state = {
  handle: null, round: null, entry: null, draft: null,
  version: null, shownResult: null, view: "play",
};
let saveTimer = null;

const topbar = createTopbar();
const room = createRoom();
const result = createResult();
const entry = createEntry({
  onDraftChange(draft) {
    state.draft = draft;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, SAVE_DEBOUNCE_MS);
  },
  onGoRoom: () => setView("room"),
  async onLock() {
    clearTimeout(saveTimer);
    await saveDraft();
    try {
      state.entry = await api.lock(state.round.round_id, `${state.round.round_id}:${state.handle}`);
      hideError();
      entry.render(state.round, state.entry, { force: true });
    } catch (err) { showError(err.message); }
  },
});

// ── routing ───────────────────────────────────────────────────────────────
// The view lives in the URL, so back/forward behave the way anyone expects
// and a view can be linked to.
function setView(name, { push = true } = {}) {
  if (!VIEWS.includes(name)) name = "play";
  state.view = name;
  VIEWS.forEach((v) => show($(`view-${v}`), v === name));
  [...$("tabs").children].forEach((tab) =>
    tab.classList.toggle("is-active", tab.dataset.view === name));
  if (push && location.hash.slice(1) !== name) location.hash = name;
}

const viewFromHash = () => location.hash.slice(1) || "play";

on($("tabs"), "click", (event) => {
  const tab = event.target.closest(".tab");
  if (tab) setView(tab.dataset.view);
});

on(window, "hashchange", () => setView(viewFromHash(), { push: false }));

on(document, "keydown", (event) => {
  if (state.view !== "play" || event.metaKey || event.ctrlKey) return;
  if (document.activeElement?.tagName === "INPUT") return;
  entry.handleKey(event.key);
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
    // A stale version means this entry moved elsewhere; re-read rather than
    // clobber it.
    if (/version/i.test(err.message)) await refresh();
    else showError(err.message);
  }
}

async function refresh() {
  try {
    const round = await api.currentRound();
    syncTo(round.server_time);
    const changed = state.round?.round_id !== round.round_id
                 || state.round?.status !== round.status;
    const firstReveal = changed && round.status === "revealed";
    state.round = round;

    state.entry = await api.entry(round.round_id);
    state.version = state.entry?.version ?? null;
    entry.render(round, state.entry, { force: changed });

    const standings = await api.standings(round.round_id);
    room.render(standings, state.entry?.vote ?? null);
    entry.showLeaders(standings);

    topbar.render(round);
    await loadResult(round);

    // The number landing is the one moment worth interrupting for.
    if (firstReveal) setView("result");
  } catch (err) { showError(err.message); }
}

/** The live round's own result once it exists, otherwise the last published. */
async function loadResult(round) {
  const current = RESOLVED.has(round.status);
  let roundId = round.round_id;
  if (!current) {
    try { roundId = (await api.latestRevealed()).round_id; }
    catch { result.empty("The first number is published at the end of this round."); return; }
  }
  if (state.shownResult === roundId) return;
  try {
    const published = await api.result(roundId);
    let mine = null;
    try { mine = await api.myResult(roundId); } catch { /* no entry that round */ }
    result.render(published, mine, { handle: state.handle, isCurrent: current });
    state.shownResult = roundId;
  } catch {
    result.empty("This round is still being counted.");
  }
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

  setView(viewFromHash(), { push: false });
  await refresh();
  setInterval(refresh, POLL_MS);
  setInterval(() => topbar.tick(state.round), TICK_MS);
}

boot();
