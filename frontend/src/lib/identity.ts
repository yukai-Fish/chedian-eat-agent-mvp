"use client";

export type CurrentIdentity = {
  anonymousId: string;
  userId: string | null;
  kind: "anonymous" | "authenticated";
};

type StoredIdentity = {
  anonymousId: string;
  userId?: string | null;
};

const IDENTITY_STORAGE_KEY = "chedian.identity.v1";

let cachedIdentity: CurrentIdentity | null = null;

function buildAnonymousId(): string {
  const randomPart =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID().replace(/-/g, "")
      : `${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
  return `anon_${randomPart.slice(0, 24)}`;
}

function normalizeStoredIdentity(raw: unknown): StoredIdentity | null {
  if (!raw || typeof raw !== "object") return null;
  const node = raw as { anonymousId?: unknown; userId?: unknown };
  const anonymousId = String(node.anonymousId || "").trim();
  if (!anonymousId) return null;
  const userId = node.userId == null ? null : String(node.userId).trim() || null;
  return { anonymousId, userId };
}

function saveIdentity(identity: StoredIdentity): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(IDENTITY_STORAGE_KEY, JSON.stringify(identity));
  } catch {
    // ignore storage failures in private mode
  }
}

export function getCurrentIdentity(): CurrentIdentity {
  if (cachedIdentity) return cachedIdentity;

  if (typeof window === "undefined") {
    cachedIdentity = {
      anonymousId: "anon_server_placeholder",
      userId: null,
      kind: "anonymous",
    };
    return cachedIdentity;
  }

  let stored: StoredIdentity | null = null;
  try {
    const raw = localStorage.getItem(IDENTITY_STORAGE_KEY);
    stored = raw ? normalizeStoredIdentity(JSON.parse(raw)) : null;
  } catch {
    stored = null;
  }

  if (!stored) {
    stored = { anonymousId: buildAnonymousId(), userId: null };
    saveIdentity(stored);
  }

  cachedIdentity = {
    anonymousId: stored.anonymousId,
    userId: stored.userId ?? null,
    kind: stored.userId ? "authenticated" : "anonymous",
  };
  return cachedIdentity;
}

export function setAuthenticatedUserId(userId: string | null): CurrentIdentity {
  const current = getCurrentIdentity();
  const next: StoredIdentity = {
    anonymousId: current.anonymousId,
    userId: userId?.trim() || null,
  };
  saveIdentity(next);
  cachedIdentity = {
    anonymousId: next.anonymousId,
    userId: next.userId ?? null,
    kind: next.userId ? "authenticated" : "anonymous",
  };
  return cachedIdentity;
}

