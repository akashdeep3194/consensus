// Server time is authoritative for every phase decision (§6.4); the local
// clock only interpolates between polls.

let skew = 0;   // serverTime - clientTime

export const syncTo = (serverTimeIso) => {
  skew = new Date(serverTimeIso).getTime() - Date.now();
};

export const now = () => Date.now() + skew;

export const until = (iso) => new Date(iso).getTime() - now();

const pad = (n) => String(n).padStart(2, "0");

/** 05:22:11 — for the countdown, where every digit column must hold still. */
export const hms = (ms) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
};

/** "5h 22m" — for prose, where seconds are noise. */
export const coarse = (ms) => {
  const m = Math.max(0, Math.floor(ms / 60000));
  const h = Math.floor(m / 60);
  return h ? `${h}h ${m % 60}m` : `${m}m`;
};

/** 04:32 — for a countdown that never reaches an hour (the standings
 * refresh window is 5 minutes), where an hour column would be dead weight. */
export const mmss = (ms) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${pad(Math.floor(s / 60))}:${pad(s % 60)}`;
};

export const clockTime = () =>
  new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
