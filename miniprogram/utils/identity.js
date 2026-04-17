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
  const accessToken = raw.accessToken ? String(raw.accessToken).trim() : "";
  const tokenType = raw.tokenType ? String(raw.tokenType).trim() : "";
  const tokenExpiresAt = Number(raw.tokenExpiresAt);

  return {
    anonymousId,
    userId: userId || null,
    accessToken: accessToken || null,
    tokenType: tokenType || null,
    tokenExpiresAt: Number.isFinite(tokenExpiresAt) ? tokenExpiresAt : null,
  };
}

function persistIdentity(next) {
  wx.setStorageSync(STORAGE_KEY, next);
}

function toIdentityView(next) {
  const isAuthenticated = Boolean(next.userId && next.accessToken);
  return {
    anonymousId: next.anonymousId,
    userId: isAuthenticated ? next.userId : null,
    uid: isAuthenticated ? next.userId : next.anonymousId,
    kind: isAuthenticated ? "authenticated" : "anonymous",
    accessToken: isAuthenticated ? next.accessToken : null,
    tokenType: isAuthenticated ? (next.tokenType || "Bearer") : null,
    tokenExpiresAt: isAuthenticated ? next.tokenExpiresAt : null,
  };
}

function isExpired(next) {
  if (!next || !next.userId || !next.accessToken) return false;
  if (!Number.isFinite(next.tokenExpiresAt) || next.tokenExpiresAt <= 0) return false;
  return Date.now() >= next.tokenExpiresAt - 30 * 1000;
}

function getCurrentIdentity() {
  const stored = normalize(wx.getStorageSync(STORAGE_KEY));
  if (!stored) {
    const next = {
      anonymousId: randomId(),
      userId: null,
      accessToken: null,
      tokenType: null,
      tokenExpiresAt: null,
    };
    persistIdentity(next);
    return toIdentityView(next);
  }

  if (isExpired(stored)) {
    const next = {
      anonymousId: stored.anonymousId,
      userId: null,
      accessToken: null,
      tokenType: null,
      tokenExpiresAt: null,
    };
    persistIdentity(next);
    return toIdentityView(next);
  }

  return toIdentityView(stored);
}

function computeTokenExpiresAt(auth) {
  if (!auth || typeof auth !== "object") return null;
  const abs = Number(auth.tokenExpiresAt);
  if (Number.isFinite(abs) && abs > Date.now()) return abs;
  const expiresIn = Number(auth.expiresIn);
  if (!Number.isFinite(expiresIn) || expiresIn <= 0) return null;
  return Date.now() + expiresIn * 1000;
}

function saveAuthenticatedIdentity(userId, anonymousId, auth = {}) {
  const stored = normalize(wx.getStorageSync(STORAGE_KEY)) || {
    anonymousId: randomId(),
    userId: null,
    accessToken: null,
    tokenType: null,
    tokenExpiresAt: null,
  };

  const token = String((auth && auth.accessToken) || "").trim();
  const next = {
    anonymousId: String(anonymousId || stored.anonymousId || randomId()).trim(),
    userId: token ? (String(userId || "").trim() || null) : null,
    accessToken: token || null,
    tokenType: token ? (String((auth && auth.tokenType) || "Bearer").trim() || "Bearer") : null,
    tokenExpiresAt: token ? computeTokenExpiresAt(auth) : null,
  };

  persistIdentity(next);
  return toIdentityView(next);
}

function clearAuthenticatedIdentity() {
  const stored = normalize(wx.getStorageSync(STORAGE_KEY)) || {
    anonymousId: randomId(),
    userId: null,
    accessToken: null,
    tokenType: null,
    tokenExpiresAt: null,
  };
  const next = {
    anonymousId: stored.anonymousId,
    userId: null,
    accessToken: null,
    tokenType: null,
    tokenExpiresAt: null,
  };
  persistIdentity(next);
  return toIdentityView(next);
}

function getAuthToken() {
  const identity = getCurrentIdentity();
  return identity && identity.kind === "authenticated" ? String(identity.accessToken || "") : "";
}

module.exports = {
  getCurrentIdentity,
  saveAuthenticatedIdentity,
  clearAuthenticatedIdentity,
  getAuthToken,
};
