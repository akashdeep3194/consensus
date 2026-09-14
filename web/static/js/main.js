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
import { createHistory } from "./views/history.js";
import { createStats } from "./views/stats.js";

const POLL_MS = 4000;
const TICK_MS = 200;
const SAVE_DEBOUNCE_MS = 450;
const VIEWS = ["play", "room", "result", "history", "rules"];
const RESOLVED = new Set(["sealed", "resolving", "revealed"]);

const state = {
  handle: null, round: null, entry: null, draft: null,
  version: null, shownResult: null, view: "play",
};
let saveTimer = null;

const topbar = createTopbar();
const room = createRoom();
const result = createResult();
const history = createHistory(() => state.handle);
// Unlike the views above, its chip is injected into #who by boot() itself
// (only once signed in) rather than existing in index.html from page load,
// so it can't bind to that element until boot() has actually created it.
let stats = null;
const entry = createEntry({
  onDraftChange(draft) {
    state.draft = draft;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, SAVE_DEBOUNCE_MS);
  },
  onGoRoom: () => setView("room"),
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
  // Past rounds never change, so this loads its first page once — not on
  // every 4s poll the way the live views do — the first time it's opened.
  if (name === "history") history.activate();
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
  if (!state.round || state.entry?.committed || !state.draft) return;
  const { prediction, vote } = state.draft;
  // Skip the round trip only when there's truly nothing to do: the draft is
  // blank AND the server's copy is already blank too. A blank draft against
  // a non-blank saved entry is a real clear (backspacing a completed slate
  // back down before ever voting) and must still be sent, or the stale
  // server-side entry can resurface on reload or the next round transition.
  const savedIsBlank = !state.entry?.prediction && state.entry?.vote == null;
  if (prediction === null && vote === null && savedIsBlank) return;
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

    // The number landing is the one moment worth interrupting for — and the
    // one moment the season total actually might have just moved.
    if (firstReveal) {
      setView("result");
      stats?.refresh();
    }
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

/** The topbar (round #, phase, countdown) needs no session — /api/rounds/current
 * is public — so a visitor still on the sign-in gate sees it too, not just
 * "Round —"/"--:--:--" until they've signed in. Errors are swallowed rather
 * than shown: #err lives inside the signed-in game view, invisible here, and
 * the next poll just tries again. */
async function refreshTopbarOnly() {
  try {
    const round = await api.currentRound();
    syncTo(round.server_time);
    state.round = round;
    topbar.render(round);
  } catch { /* transient — next poll retries */ }
}

// ── boot ──────────────────────────────────────────────────────────────────
async function boot() {
  const me = await api.me();
  state.handle = me.handle;

  // The server refuses to act on this button at all outside DEV_LOGIN=1
  // (api.main.require_admin) — hiding it in production isn't the security
  // boundary, just not showing a control that would 401 for every visitor.
  show($("advance"), !!me.dev_enabled);

  if (!state.handle) {
    show($("gate"), true);
    if (me.dev_enabled) {
      show($("dev-gate"), true);
    }
    if (!me.google_enabled) {
      const googleBtn = $("google-login-btn");
      if (googleBtn) {
        googleBtn.title = "Google OAuth is not configured on this server.";
      }
    }
    await refreshTopbarOnly();
    setInterval(refreshTopbarOnly, POLL_MS);
    setInterval(() => topbar.tick(state.round), TICK_MS);
    return;
  }


  show($("gate"), false);
  show($("game"), true);
  $("who").innerHTML = `<span class="who__handle">${esc(state.handle)}</span>
    <button class="who__points" id="myPoints" type="button">— pts</button>
    <button class="btn btn--ghost" id="signout" type="button">Sign out</button>`;
  on($("signout"), "click", async () => { await api.signOut(); location.reload(); });
  stats = createStats();
  stats.refresh();

  setView(viewFromHash(), { push: false });
  await refresh();
  setInterval(refresh, POLL_MS);
  setInterval(() => topbar.tick(state.round), TICK_MS);
  setInterval(() => room.tick(), TICK_MS);
}

boot();
