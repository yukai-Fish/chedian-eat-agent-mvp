const { trackUsageEvent } = require("./api");
const { getCurrentIdentity } = require("./identity");

function trimOptional(value, maxLength) {
  if (value === undefined || value === null) return undefined;
  const text = String(value || "").trim();
  if (!text) return undefined;
  return text.slice(0, maxLength);
}

function normalizeMeta(meta) {
  if (!meta || typeof meta !== "object" || Array.isArray(meta)) return undefined;
  const next = {};
  Object.keys(meta).forEach((rawKey) => {
    const key = trimOptional(rawKey, 40);
    if (!key) return;
    const value = meta[rawKey];
    if (value === undefined || value === null) return;

    if (typeof value === "string") {
      const text = trimOptional(value, 300);
      if (text) next[key] = text;
      return;
    }

    if (typeof value === "number" || typeof value === "boolean") {
      next[key] = value;
      return;
    }

    if (Array.isArray(value)) {
      next[key] = value.slice(0, 20).map((item) => String(item || "").slice(0, 80));
      return;
    }

    try {
      next[key] = JSON.stringify(value).slice(0, 400);
    } catch (_err) {
      // ignore non-serializable meta fields
    }
  });

  return Object.keys(next).length ? next : undefined;
}

function trackEvent(payload) {
  const identity = getCurrentIdentity();
  const body = {
    eventType: trimOptional(payload && payload.eventType, 80),
    uid: trimOptional(payload && payload.uid, 120) || trimOptional(identity && identity.uid, 120),
    anonymousId:
      trimOptional(payload && payload.anonymousId, 80) || trimOptional(identity && identity.anonymousId, 80),
    userId: trimOptional(payload && payload.userId, 120) || trimOptional(identity && identity.userId, 120),
    queryText: trimOptional(payload && payload.queryText, 300),
    shopId: trimOptional(payload && payload.shopId, 120),
    shopName: trimOptional(payload && payload.shopName, 120),
    source: trimOptional(payload && payload.source, 60) || "miniprogram",
    meta: normalizeMeta(payload && payload.meta),
  };

  if (!body.eventType) {
    return Promise.resolve({ ok: false, skipped: true });
  }

  return trackUsageEvent(body).catch(() => ({ ok: false }));
}

module.exports = {
  trackEvent,
};
