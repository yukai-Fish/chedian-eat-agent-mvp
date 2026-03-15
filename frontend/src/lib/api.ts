export type HistoryMessage = {
  role: "user" | "assistant";
  contentType?: "text" | "image";
  content: string;
};

export type RecommendProxyRequest = {
  query: string;
  uid?: string;
  chatId?: string;
  stream?: boolean;
  parameters?: Record<string, unknown>;
  history?: HistoryMessage[];
};

export type RecommendProxyResponse = {
  ok: boolean;
  answer?: string | null;
  raw?: unknown;
  error?: string | null;
  code?: number | null;
  finishReason?: string | null;
};

export type WorkflowResumeRequest = {
  eventId: string;
  eventType?: "resume" | "ignore" | "abort";
  content?: string;
  stream?: boolean;
};

export type WorkflowUploadFileResponse = {
  ok: boolean;
  url?: string | null;
  raw?: unknown;
  error?: string | null;
  code?: number | null;
};

export type HotRankingItem = {
  rank: number;
  shop_id: string;
  name: string;
  tag: string;
  campus: string;
  avg_price: number;
  query: string;
  trend: "up" | "down" | "flat";
  delta: number;
  today_count: number;
  yesterday_count: number;
};

export type HotRankingResponse = {
  updated_at: string;
  source: string;
  items: HotRankingItem[];
};

export type RankingClickPayload = {
  shopId: string;
  shopName?: string;
  uid?: string;
};

export type FeedbackType = "new_store" | "dining_feedback";

export type FeedbackPayload = {
  feedbackType: FeedbackType;
  storeName: string;
  area?: string;
  category?: string;
  avgPrice?: number;
  rating?: number;
  sceneTags?: string[];
  tasteTags?: string[];
  featureTags?: string[];
  recommendDish?: string;
  shortIntro?: string;
  recommendReason?: string;
  comment?: string;
  warningNote?: string;
  source?: string;
};

export type FeedbackResponse = {
  ok: boolean;
  id?: number;
  message: string;
};

const PROD_API_FALLBACK = "https://chedian-eat-agent-mvp.onrender.com";

function resolveApiBaseUrl(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (fromEnv) return fromEnv;

  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      return "http://localhost:8000";
    }
  }

  // Safe production fallback when Netlify env var is missing.
  return PROD_API_FALLBACK;
}

const API_BASE_URL = resolveApiBaseUrl();

export async function fetchRecommendations(payload: RecommendProxyRequest): Promise<RecommendProxyResponse> {
  const res = await fetch(`${API_BASE_URL}/api/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }

  return res.json();
}

export async function fetchTodayHotRanking(): Promise<HotRankingItem[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/rankings/today`, {
    method: "GET",
  });

  if (!res.ok) {
    throw new Error(`Ranking request failed: ${res.status}`);
  }

  const data = (await res.json()) as HotRankingResponse;
  return data.items || [];
}

export async function resumeRecommendations(payload: WorkflowResumeRequest): Promise<RecommendProxyResponse> {
  const res = await fetch(`${API_BASE_URL}/api/recommend/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`Resume request failed: ${res.status}`);
  }

  return res.json();
}

export async function uploadWorkflowFile(file: File): Promise<WorkflowUploadFileResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}/api/workflow/upload-file`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    throw new Error(`Upload request failed: ${res.status}`);
  }

  return res.json();
}

export async function reportRankingClick(payload: RankingClickPayload): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/api/v1/events/ranking-click`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        shop_id: payload.shopId,
        shop_name: payload.shopName,
        uid: payload.uid,
      }),
    });
  } catch {
    // Non-blocking analytics event.
  }
}

export async function submitFeedback(payload: FeedbackPayload): Promise<FeedbackResponse> {
  const res = await fetch(`${API_BASE_URL}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail || "反馈提交失败，请稍后重试。");
  }

  return (await res.json()) as FeedbackResponse;
}

export async function fetchStoreNameSuggestions(keyword: string): Promise<string[]> {
  const k = keyword.trim();
  if (!k) return [];
  const res = await fetch(`${API_BASE_URL}/api/stores/suggest?keyword=${encodeURIComponent(k)}`, {
    method: "GET",
  });
  if (!res.ok) return [];
  const data = (await res.json()) as { items?: string[] };
  return data.items || [];
}
