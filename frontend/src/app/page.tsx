"use client";

import { startTransition, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import Image from "next/image";

import { FeedbackPanel } from "@/components/FeedbackPanel";
import { parseAnswerToRecommendationResult } from "@/lib/answerFormatter";
import {
  fetchRecommendations,
  fetchTodayHotRanking,
  reportRankingClick,
  resumeRecommendations,
  type HistoryMessage,
  type HotRankingItem,
} from "@/lib/api";

const QUICK_PROMPTS = [
  "清水河附近，预算 25，一个人，想吃清淡一点",
  "沙河校区，晚上和室友聚餐，预算 35，想吃辣",
  "现在在清水河，夜宵有什么性价比高的推荐？",
  "中午赶时间，预算 20 内，离教学楼近一点",
];

const CAMPUS_HOT_RANKING_FALLBACK: HotRankingItem[] = [
  { rank: 1, shop_id: "kw-night", name: "#夜宵", tag: "等待更多搜索数据", campus: "", avg_price: 0, query: "清水河附近，夜宵有什么推荐？", trend: "flat", delta: 0, today_count: 0, yesterday_count: 0 },
  { rank: 2, shop_id: "kw-single", name: "#一个人", tag: "等待更多搜索数据", campus: "", avg_price: 0, query: "一个人吃，预算 25 左右，有什么推荐？", trend: "flat", delta: 0, today_count: 0, yesterday_count: 0 },
  { rank: 3, shop_id: "kw-light", name: "#清淡", tag: "等待更多搜索数据", campus: "", avg_price: 0, query: "不辣清淡一点，有哪些推荐？", trend: "flat", delta: 0, today_count: 0, yesterday_count: 0 },
  { rank: 4, shop_id: "kw-group", name: "#聚餐", tag: "等待更多搜索数据", campus: "", avg_price: 0, query: "晚上和同学聚餐，预算 40 左右推荐什么？", trend: "flat", delta: 0, today_count: 0, yesterday_count: 0 },
  { rank: 5, shop_id: "kw-value", name: "#性价比", tag: "等待更多搜索数据", campus: "", avg_price: 0, query: "清水河附近，性价比高的店有哪些？", trend: "flat", delta: 0, today_count: 0, yesterday_count: 0 },
];

const getTrendMeta = (trend: HotRankingItem["trend"], delta: number) => {
  if (trend === "up") {
    return { arrow: "↑", text: `较昨日 +${Math.abs(delta)}`, cls: "up" as const };
  }
  if (trend === "down") {
    return { arrow: "↓", text: `较昨日 -${Math.abs(delta)}`, cls: "down" as const };
  }
  return { arrow: "→", text: "较昨日 持平", cls: "flat" as const };
};

type QuerySignal = {
  label: string;
  value: string;
};

type WorkflowTraceItem = {
  ts?: string;
  step?: string;
  status?: string;
  retryable?: string;
  detail?: string;
  code?: string;
  finish_reason?: string;
};

type WorkflowInterruptState = {
  eventId: string;
  needReply: boolean;
  mode: "direct" | "option";
  prompt: string;
  options: string[];
};

const extractTrace = (raw: unknown): WorkflowTraceItem[] => {
  const trace = (raw as { _trace?: unknown } | null | undefined)?._trace;
  if (!Array.isArray(trace)) return [];
  return trace.filter((item): item is WorkflowTraceItem => typeof item === "object" && item !== null);
};

const extractInterrupt = (raw: unknown, finishReason?: string | null): WorkflowInterruptState | null => {
  if (finishReason !== "interrupt") return null;

  const eventData = (raw as { event_data?: unknown } | null | undefined)?.event_data;
  if (!eventData || typeof eventData !== "object") return null;

  const normalized = eventData as {
    event_id?: unknown;
    event_type?: unknown;
    need_reply?: unknown;
    value?: {
      type?: unknown;
      content?: unknown;
      option?: unknown;
    };
  };
  if (normalized.event_type !== "interrupt") return null;

  const eventId = String(normalized.event_id || "").trim();
  if (!eventId) return null;

  const value = normalized.value || {};
  const mode = value.type === "option" ? "option" : "direct";
  const prompt = String(value.content || "").trim() || "工作流需要你补充信息后继续。";
  const rawOptions = Array.isArray(value.option) ? value.option : [];
  const options = rawOptions
    .map((item) => {
      if (typeof item === "string") return item.trim();
      if (!item || typeof item !== "object") return "";
      const node = item as { content?: unknown; label?: unknown; value?: unknown };
      return String(node.content || node.label || node.value || "").trim();
    })
    .filter(Boolean);

  return {
    eventId,
    needReply: Boolean(normalized.need_reply),
    mode,
    prompt,
    options,
  };
};

const signalRule = (query: string): QuerySignal[] => {
  const signals: QuerySignal[] = [];
  const text = query.trim();
  if (!text) return signals;

  if (text.includes("清水河")) signals.push({ label: "校区", value: "清水河" });
  else if (text.includes("沙河")) signals.push({ label: "校区", value: "沙河" });

  const budgetMatch = text.match(/预算\s*([0-9]{1,3})/);
  if (budgetMatch?.[1]) signals.push({ label: "预算", value: `¥${budgetMatch[1]}以内` });

  if (/(夜宵|晚上|晚饭)/.test(text)) signals.push({ label: "场景", value: "夜间就餐" });
  else if (/(中午|午饭|赶时间)/.test(text)) signals.push({ label: "场景", value: "午间快餐" });
  else if (/(聚餐|室友|同学)/.test(text)) signals.push({ label: "场景", value: "多人聚餐" });
  else if (/(一个人|一人食)/.test(text)) signals.push({ label: "场景", value: "一人食" });

  if (/(不辣|清淡)/.test(text)) signals.push({ label: "口味", value: "清淡少辣" });
  else if (/(辣|重口)/.test(text)) signals.push({ label: "口味", value: "偏辣重口" });

  return signals.slice(0, 4);
};

const buildHighlight = (reason: string) => {
  const parts = reason
    .split(/[。.!！?？；;]/)
    .map((item) => item.trim())
    .filter(Boolean);
  return parts[0] || reason;
};

const displayOrFallback = (value: string, fallback = "未提供") => {
  const text = (value || "").trim();
  return text || fallback;
};

export default function HomePage() {
  const [query, setQuery] = useState("预算30，清水河，晚上和同学想吃辣的");
  const [history, setHistory] = useState<HistoryMessage[]>([]);
  const [answer, setAnswer] = useState("");
  const [chatId, setChatId] = useState<string | undefined>(undefined);
  const [uid] = useState("demo-user");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorTrace, setErrorTrace] = useState<WorkflowTraceItem[]>([]);
  const [interruptState, setInterruptState] = useState<WorkflowInterruptState | null>(null);
  const [resumeInput, setResumeInput] = useState("");
  const [resumeLoading, setResumeLoading] = useState(false);
  const [rankingOpen, setRankingOpen] = useState(false);
  const [rankingItems, setRankingItems] = useState<HotRankingItem[]>(CAMPUS_HOT_RANKING_FALLBACK);
  const [rankingLoading, setRankingLoading] = useState(false);
  const [isComposerFocused, setIsComposerFocused] = useState(false);
  const [resultTransitionKey, setResultTransitionKey] = useState(0);
  const [currentBatchIndex, setCurrentBatchIndex] = useState(0);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const rankingWrapRef = useRef<HTMLDivElement>(null);
  const rankingLoadRef = useRef<(() => Promise<void>) | null>(null);

  const parsedRecommendation = useMemo(() => parseAnswerToRecommendationResult(answer), [answer]);
  const cards = parsedRecommendation.cards;
  const isStructured = parsedRecommendation.mode === "structured";
  const batchSize = isStructured ? Math.max(1, parsedRecommendation.batchSize) : 3;
  const batchCount = isStructured ? Math.max(1, Math.ceil(cards.length / batchSize)) : 1;
  const normalizedBatchIndex = batchCount > 0 ? currentBatchIndex % batchCount : 0;
  const visibleCards = useMemo(() => {
    if (!cards.length) return [];
    if (!isStructured) return cards.slice(0, 3);
    const start = normalizedBatchIndex * batchSize;
    return cards.slice(start, start + batchSize);
  }, [cards, isStructured, normalizedBatchIndex, batchSize]);
  const querySignals = useMemo(() => signalRule(query), [query]);
  const primaryCard = visibleCards[0];
  const secondaryCards = visibleCards.slice(1, 3);
  const primaryHighlight = useMemo(() => buildHighlight(primaryCard?.reason || ""), [primaryCard]);
  const showPrimaryReasonDetail = useMemo(() => {
    if (!primaryCard) return false;
    const compactReason = primaryCard.reason.replace(/[。.!！?？；;\s]+/g, "");
    const compactHighlight = primaryHighlight.replace(/[。.!！?？；;\s]+/g, "");
    return compactReason !== compactHighlight;
  }, [primaryCard, primaryHighlight]);
  const submitHint = useMemo(() => {
    if (typeof navigator === "undefined") {
      return "Enter 发送 · Shift+Enter 换行";
    }
    const isMac = /Mac|iPhone|iPad/i.test(navigator.platform);
    return isMac ? "Enter 发送 · Shift+Enter 换行 · Cmd+Enter 快速发送" : "Enter 发送 · Shift+Enter 换行 · Ctrl+Enter 快速发送";
  }, []);

  const submitQuery = async (nextQuery: string) => {
    const text = nextQuery.trim();
    if (!text || loading) return;

    try {
      setLoading(true);
      setError(null);
      setErrorTrace([]);
      setInterruptState(null);

      const res = await fetchRecommendations({
        query: text,
        uid,
        chatId,
        history,
      });

      if (!res.ok) {
        const raw = (res.raw as { chat_id?: string } | undefined) || undefined;
        if (raw?.chat_id) {
          setChatId(raw.chat_id);
        }

        const interrupt = extractInterrupt(res.raw, res.finishReason);
        if (interrupt) {
          setInterruptState(interrupt);
          setResumeInput(interrupt.mode === "option" && interrupt.options[0] ? interrupt.options[0] : "");
          setHistory((prev) => [...prev, { role: "user", content: text }]);
          return;
        }

        setError(res.error || "暂时没有拿到推荐结果，请稍后再试。");
        setErrorTrace(extractTrace(res.raw));
        return;
      }

      const nextAnswer = (res.answer || "").trim();
      setAnswer(nextAnswer);
      setCurrentBatchIndex(0);
      setHistory((prev) => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: nextAnswer },
      ]);

      const raw = (res.raw as { chat_id?: string } | undefined) || undefined;
      if (raw?.chat_id) {
        setChatId(raw.chat_id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求失败，请检查网络后重试。");
      setErrorTrace([]);
    } finally {
      setLoading(false);
    }
  };

  const handleResume = async (eventType: "resume" | "ignore" | "abort") => {
    if (!interruptState || resumeLoading) return;

    const content = resumeInput.trim();
    if (eventType === "resume" && interruptState.needReply && !content) {
      setError("该中断节点需要回复内容后才能继续。");
      return;
    }

    try {
      setResumeLoading(true);
      setError(null);
      setErrorTrace([]);

      const res = await resumeRecommendations({
        eventId: interruptState.eventId,
        eventType,
        content,
      });

      if (!res.ok) {
        const nextInterrupt = extractInterrupt(res.raw, res.finishReason);
        if (nextInterrupt) {
          setInterruptState(nextInterrupt);
          setResumeInput(nextInterrupt.mode === "option" && nextInterrupt.options[0] ? nextInterrupt.options[0] : "");
          return;
        }
        setError(res.error || "恢复工作流失败，请稍后重试。");
        setErrorTrace(extractTrace(res.raw));
        return;
      }

      const nextAnswer = (res.answer || "").trim();
      setAnswer(nextAnswer);
      setCurrentBatchIndex(0);
      setInterruptState(null);
      setResumeInput("");
      setHistory((prev) => {
        const resumeLabel =
          eventType === "resume" ? content || "[继续]" : eventType === "ignore" ? "[忽略并继续]" : "[终止]";
        return [...prev, { role: "user", content: resumeLabel }, { role: "assistant", content: nextAnswer }];
      });

      const raw = (res.raw as { chat_id?: string } | undefined) || undefined;
      if (raw?.chat_id) {
        setChatId(raw.chat_id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "恢复工作流失败，请检查网络后重试。");
      setErrorTrace([]);
    } finally {
      setResumeLoading(false);
    }
  };

  const onSubmit = async () => {
    await submitQuery(query);
  };

  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      const node = rankingWrapRef.current;
      if (!node || !rankingOpen) return;
      if (!node.contains(event.target as Node)) {
        setRankingOpen(false);
      }
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setRankingOpen(false);
        setFeedbackOpen(false);
      }
    };

    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [rankingOpen]);

  useEffect(() => {
    if (!feedbackOpen) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, [feedbackOpen]);

  useEffect(() => {
    if (!rankingOpen) return;
    let canceled = false;

    const loadRanking = async () => {
      try {
        setRankingLoading(true);
        const items = await fetchTodayHotRanking();
        if (!canceled && items.length > 0) {
          setRankingItems(items);
        }
      } catch {
        // Keep fallback ranking silently.
      } finally {
        if (!canceled) {
          setRankingLoading(false);
        }
      }
    };
    rankingLoadRef.current = loadRanking;

    void loadRanking();
    const timer = window.setInterval(() => {
      void loadRanking();
    }, 45_000);

    return () => {
      canceled = true;
      rankingLoadRef.current = null;
      window.clearInterval(timer);
    };
  }, [rankingOpen]);

  useEffect(() => {
    if (!answer) return;
    setResultTransitionKey((prev) => prev + 1);
  }, [answer, normalizedBatchIndex]);

  return (
    <main className="demo-page">
      <div className="atmo-layer atmo-wash" />
      <div className="leaf-layer leaf-primary" />
      <div className="leaf-layer leaf-secondary" />
      <div className="leaf-layer leaf-tertiary" />
      <div className="emblem-ambient" />

      <div className="demo-shell">
        <section className="hero-card">
          <div className="hero-top">
            <div className="hero-badge">Campus AI Food Agent</div>
            <div className="emblem-widget" ref={rankingWrapRef}>
              <button
                type="button"
                className="school-badge school-badge-btn"
                aria-label="电子科技大学校徽"
                aria-expanded={rankingOpen}
                onClick={() => setRankingOpen((v) => !v)}
              >
                <span className="school-badge-icon">
                  <Image src="/image/xiaohui.png" alt="UESTC Emblem" width={36} height={36} priority />
                </span>
                <span className="school-badge-text">
                  <b>UESTC</b>
                  <em>电子科技大学</em>
                </span>
                <span className={`badge-caret ${rankingOpen ? "open" : ""}`} aria-hidden>
                  ▾
                </span>
              </button>

              <section className={`ranking-popover ${rankingOpen ? "open" : ""}`} aria-hidden={!rankingOpen}>
                <div className="ranking-head">
                  <div className="ranking-head-main">
                    <h3>今日热门美食榜</h3>
                    <p>看看同学们今天都在吃什么</p>
                  </div>
                  <button
                    type="button"
                    className="ranking-refresh-btn"
                    onClick={() => {
                      if (!rankingLoading) {
                        void rankingLoadRef.current?.();
                      }
                    }}
                    disabled={rankingLoading}
                    aria-label="刷新热门榜"
                  >
                    <span className={`refresh-icon ${rankingLoading ? "spinning" : ""}`} aria-hidden>
                      ↻
                    </span>
                    刷新
                  </button>
                </div>
                {rankingLoading && <div className="ranking-loading">正在更新今日榜单...</div>}
                <div className="ranking-list">
                  {rankingItems.map((item, idx) => {
                    const trendMeta = getTrendMeta(item.trend, item.delta);
                    return (
                      <button
                        key={item.shop_id || item.name}
                        type="button"
                        className={`rank-item rank-${idx + 1}`}
                        style={{ "--rank-delay": `${idx * 45}ms` } as CSSProperties}
                        onClick={() => {
                          void reportRankingClick({
                            shopId: item.shop_id,
                            shopName: item.name,
                            uid,
                          });
                          setQuery(item.query);
                          setRankingOpen(false);
                        }}
                      >
                        <span className="rank-no">{idx + 1}</span>
                        <span className="rank-main">
                          <strong>
                            {item.name}
                            <span className={`rank-trend rank-trend-${trendMeta.cls}`}>{trendMeta.arrow}</span>
                          </strong>
                          <em>{item.tag}</em>
                          <small className={`rank-trend-text rank-trend-${trendMeta.cls}`}>{trendMeta.text}</small>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </section>
            </div>
          </div>
          <h1>成电吃什么</h1>
          <p>你的校园吃饭决策助手，帮你在预算、口味、距离和场景之间快速做出更优选择。</p>
          <div className="hero-stats">
            <span>清水河 / 沙河</span>
            <span>多轮会话推荐</span>
            <span>结构化卡片展示</span>
          </div>
        </section>

        <section className="composer-card">
          <div className="composer-title">今天想怎么吃？</div>
          <div className="signal-row" aria-live="polite">
            {querySignals.length > 0 ? (
              querySignals.map((item) => (
                <span className="signal-chip" key={`${item.label}-${item.value}`}>
                  <b>{item.label}</b>
                  <em>{item.value}</em>
                </span>
              ))
            ) : (
              <span className="signal-tip">输入后自动识别条件：校区 / 预算 / 场景 / 口味</span>
            )}
          </div>
          <div className={`composer-input-wrap ${isComposerFocused ? "is-focused" : ""} ${loading ? "is-loading" : ""}`}>
            <textarea
              className="composer-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => setIsComposerFocused(true)}
              onBlur={() => setIsComposerFocused(false)}
              placeholder="例如：预算 30，清水河，2 个人，不太辣，想找晚饭"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey || !e.shiftKey)) {
                  e.preventDefault();
                  void onSubmit();
                }
              }}
            />
            <button className="send-btn" onClick={() => void onSubmit()} disabled={loading || !query.trim()} aria-busy={loading}>
              {loading ? "生成中..." : "发送"}
            </button>
          </div>
          <div className="composer-foot">
            <span className="submit-hint">{submitHint}</span>
            <div className="composer-foot-actions">
              {loading && <span className="submit-feedback">正在理解你的偏好并匹配结果...</span>}
              <button
                type="button"
                className="feedback-entry-btn"
                onClick={() => setFeedbackOpen(true)}
              >
                <span aria-hidden>✦</span>
                反馈新店 / 用餐体验
              </button>
            </div>
          </div>
          <div className="chip-row">
            {QUICK_PROMPTS.map((item) => (
              <button
                key={item}
                className={`chip-btn ${query.trim() === item ? "is-active" : ""}`}
                onClick={() => {
                  setQuery(item);
                  void submitQuery(item);
                }}
                disabled={loading}
              >
                {item}
              </button>
            ))}
          </div>
        </section>

        {error && (
          <section className="state-card state-error">
            <h3>出错了</h3>
            <p>{error}</p>
            {errorTrace.length > 0 && (
              <details className="raw-answer">
                <summary>查看后端追踪（_trace）</summary>
                <pre>{JSON.stringify(errorTrace, null, 2)}</pre>
              </details>
            )}
          </section>
        )}

        {interruptState && (
          <section className="state-card state-interrupt">
            <h3>需要补充信息</h3>
            <p>{interruptState.prompt}</p>
            {interruptState.options.length > 0 && (
              <div className="interrupt-options">
                {interruptState.options.map((item) => (
                  <button
                    key={item}
                    type="button"
                    className={`chip-btn ${resumeInput === item ? "is-active" : ""}`}
                    onClick={() => setResumeInput(item)}
                    disabled={resumeLoading}
                  >
                    {item}
                  </button>
                ))}
              </div>
            )}
            <div className="interrupt-input-wrap">
              <input
                className="interrupt-input"
                placeholder={interruptState.needReply ? "请输入补充信息后继续" : "可选填写补充信息"}
                value={resumeInput}
                onChange={(e) => setResumeInput(e.target.value)}
                disabled={resumeLoading}
              />
              <div className="interrupt-actions">
                <button type="button" className="send-btn" onClick={() => void handleResume("resume")} disabled={resumeLoading}>
                  {resumeLoading ? "处理中..." : "继续"}
                </button>
                <button
                  type="button"
                  className="feedback-entry-btn"
                  onClick={() => void handleResume("ignore")}
                  disabled={resumeLoading}
                >
                  忽略
                </button>
                <button
                  type="button"
                  className="feedback-entry-btn"
                  onClick={() => void handleResume("abort")}
                  disabled={resumeLoading}
                >
                  终止
                </button>
              </div>
            </div>
          </section>
        )}

        <section className="content-grid">
          <div className="results-panel results-panel-full">
            <div className="section-head">
              <h2>推荐结果</h2>
              <div className="result-actions">
                <span>
                  {loading
                    ? "正在为你匹配最优选项..."
                    : parsedRecommendation.summary || "优先展示最匹配选项，其次给你备选"}
                </span>
                {isStructured && cards.length > batchSize && (
                  <button
                    type="button"
                    className="refresh-batch-btn"
                    onClick={() => {
                      startTransition(() => {
                        setCurrentBatchIndex((prev) => (prev + 1) % batchCount);
                      });
                    }}
                  >
                    换一批
                  </button>
                )}
                {parsedRecommendation.parseError && <span className="result-fallback-note">工作流未返回可解析的 JSON，以下为原始回答</span>}
              </div>
            </div>

            {loading && (
              <div className="result-stack">
                <article className="result-card result-card-primary skeleton">
                  <div className="skeleton-line lg" />
                  <div className="skeleton-line" />
                  <div className="skeleton-line" />
                  <div className="skeleton-tags">
                    <span />
                    <span />
                    <span />
                  </div>
                </article>
                <div className="secondary-grid">
                  {[0, 1].map((idx) => (
                    <article className="result-card result-card-secondary skeleton" key={idx}>
                      <div className="skeleton-line lg" />
                      <div className="skeleton-line" />
                      <div className="skeleton-line" />
                      <div className="skeleton-tags">
                        <span />
                        <span />
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            )}

            {!loading && !answer && !error && (
              <section className="state-card">
                <h3>准备就绪</h3>
                <p>输入你的需求，系统会给出适合校园场景的推荐，并自动整理成可展示卡片。</p>
              </section>
            )}

            {!loading && answer && primaryCard && (
              <>
                <div className="result-stack" key={resultTransitionKey}>
                  <article className="result-card result-card-primary">
                    <div className="result-head">
                      <h3>{primaryCard.name}</h3>
                      <div className="result-head-right">
                        {typeof primaryCard.score === "number" && (
                          <span className="score-chip">{primaryCard.score}% 匹配</span>
                        )}
                        <span className="rank-tag champion">BEST MATCH</span>
                      </div>
                    </div>
                    <p className="primary-highlight">{displayOrFallback(primaryHighlight, "未提供推荐理由")}</p>
                    <div className="tag-list">
                      {primaryCard.tags.map((tag) => (
                        <span className="tag" key={`${primaryCard.name}-${tag}`}>
                          {tag}
                        </span>
                      ))}
                    </div>
                    <ul className="meta-list">
                      {showPrimaryReasonDetail && (
                        <li>
                          <strong>推荐理由</strong>
                        <p>{displayOrFallback(primaryCard.reason, "未提供推荐理由")}</p>
                        </li>
                      )}
                      <li>
                        <strong>推荐菜</strong>
                        <p>{displayOrFallback(primaryCard.dishes)}</p>
                      </li>
                      <li>
                        <strong>适合场景</strong>
                        <p>{displayOrFallback(primaryCard.scene)}</p>
                      </li>
                      <li>
                        <strong>可能不足</strong>
                        <p>{displayOrFallback(primaryCard.downside)}</p>
                      </li>
                    </ul>
                  </article>

                  <div className="secondary-grid">
                    {secondaryCards.map((card, idx) => (
                      <article className="result-card result-card-secondary" key={`${card.name}-${idx + 1}`} style={{ "--card-delay": `${140 + idx * 70}ms` } as CSSProperties}>
                        <div className="result-head">
                          <h3>{card.name}</h3>
                          <div className="result-head-right">
                            {typeof card.score === "number" && (
                              <span className="score-chip">{card.score}% 匹配</span>
                            )}
                            <span className="rank-tag">TOP {idx + 2}</span>
                          </div>
                        </div>
                        <p className="secondary-highlight">{displayOrFallback(buildHighlight(card.reason), "未提供推荐理由")}</p>
                        <div className="tag-list">
                          {card.tags.map((tag) => (
                            <span className="tag" key={`${card.name}-${tag}`}>
                              {tag}
                            </span>
                          ))}
                        </div>
                        <ul className="meta-list compact">
                          <li>
                            <strong>推荐菜</strong>
                            <p>{displayOrFallback(card.dishes)}</p>
                          </li>
                          <li>
                            <strong>适合场景</strong>
                            <p>{displayOrFallback(card.scene)}</p>
                          </li>
                          <li>
                            <strong>可能不足</strong>
                            <p>{displayOrFallback(card.downside)}</p>
                          </li>
                        </ul>
                      </article>
                    ))}
                  </div>
                </div>

                <details className="raw-answer">
                  <summary>查看模型原始回答</summary>
                  <pre>{answer}</pre>
                </details>
              </>
            )}

            {!loading && answer && !primaryCard && (
              <section className="state-card">
                <h3>已返回结果</h3>
                <p>当前回答暂时无法结构化为店铺卡片，请展开原始回答查看完整内容。</p>
                <details className="raw-answer">
                  <summary>查看模型原始回答</summary>
                  <pre>{answer}</pre>
                </details>
              </section>
            )}
          </div>
        </section>
      </div>

      <div
        className={`feedback-modal ${feedbackOpen ? "open" : ""}`}
        aria-hidden={!feedbackOpen}
        onClick={() => setFeedbackOpen(false)}
      >
        <div className="feedback-modal-scrim" />
        <section
          className="feedback-modal-panel"
          role="dialog"
          aria-modal="true"
          aria-label="校园美食反馈"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="feedback-modal-head">
            <div>
              <h3>校园美食共创</h3>
              <p>帮助更新校园美食地图，让推荐更懂同学口味。</p>
            </div>
            <button
              type="button"
              className="feedback-modal-close"
              aria-label="关闭反馈面板"
              onClick={() => setFeedbackOpen(false)}
            >
              ×
            </button>
          </div>
          <div className="feedback-modal-body">
            <FeedbackPanel showHeader={false} />
          </div>
        </section>
      </div>
    </main>
  );
}
