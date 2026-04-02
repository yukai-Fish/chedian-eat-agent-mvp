const STORAGE_KEY = "chedian.identity.v1";

function randomId() {
  const now = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 14);
  return `anon_${now}${rand}`.slice(0, 28);
}

function normalize(raw) {
  if (!raw || typeof raw !== "object") return null;
  const anonymousId = String(raw.anonymousId || "").trim();
  if (!anonymousId) return null;
  const userId = raw.userId ? String(raw.userId).trim() : "";
  return {
    anonymousId,
    userId: userId || null,
  };
}

function getCurrentIdentity() {
  const stored = normalize(wx.getStorageSync(STORAGE_KEY));
  if (stored) {
    return {
      anonymousId: stored.anonymousId,
      userId: stored.userId,
      uid: stored.userId || stored.anonymousId,
      kind: stored.userId ? "authenticated" : "anonymous",
    };
  }

  const next = { anonymousId: randomId(), userId: null };
  wx.setStorageSync(STORAGE_KEY, next);
  return {
    anonymousId: next.anonymousId,
    userId: null,
    uid: next.anonymousId,
    kind: "anonymous",
  };
}

module.exports = {
  getCurrentIdentity,
};
