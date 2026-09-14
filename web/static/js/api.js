// HTTP transport. The only module that knows a URL.

class ApiError extends Error {}

async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* non-JSON error body */ }
    throw new ApiError(detail);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  me:             () => request("GET", "/api/me"),
  signIn:     (handle) => request("POST", "/api/session", { handle }),
  signOut:        () => request("DELETE", "/api/session"),
  currentRound:   () => request("GET", "/api/rounds/current"),
  latestRevealed: () => request("GET", "/api/rounds/latest-revealed"),
  entry:      (round) => request("GET", `/api/rounds/${round}/entry`),
  saveDraft: (round, draft) => request("PUT", `/api/rounds/${round}/draft`, draft),
  standings:  (round) => request("GET", `/api/rounds/${round}/standings`),
  result:     (round) => request("GET", `/api/rounds/${round}/result`),
  myResult:   (round) => request("GET", `/api/rounds/${round}/my-result`),
  advanceClock:   () => request("POST", "/api/admin/advance"),
  history: ({ beforeCycle, limit } = {}) => {
    const q = new URLSearchParams();
    if (beforeCycle != null) q.set("before_cycle", beforeCycle);
    if (limit != null) q.set("limit", limit);
    const qs = q.toString();
    return request("GET", `/api/rounds/history${qs ? `?${qs}` : ""}`);
  },
  mySeason:  () => request("GET", "/api/me/season"),
  myResults: (roundIds) => request("GET", `/api/me/results?round_ids=${roundIds.join(",")}`),
};
