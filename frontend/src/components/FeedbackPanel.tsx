"use client";

import { useEffect, useMemo, useState } from "react";

import {
  fetchStoreNameSuggestions,
  submitFeedback,
  type FeedbackPayload,
} from "@/lib/api";

const SCENE_OPTIONS = ["一人食", "聚餐", "夜宵", "约会", "赶时间"];
const TASTE_OPTIONS = ["不辣", "微辣", "清淡", "重口味"];
const FEATURE_OPTIONS = ["分量大", "性价比高", "环境好", "出餐快", "容易排队"];

type Mode = "new_store" | "dining_feedback";

const toggleTag = (list: string[], value: string) => {
  if (list.includes(value)) {
    return list.filter((item) => item !== value);
  }
  return [...list, value];
};

type FeedbackPanelProps = {
  showHeader?: boolean;
  anonymousId?: string;
  userId?: string;
};

export function FeedbackPanel({ showHeader = true, anonymousId, userId }: FeedbackPanelProps) {
  const [mode, setMode] = useState<Mode>("new_store");
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  const [newStoreForm, setNewStoreForm] = useState({
    storeName: "",
    area: "",
    category: "",
    avgPrice: "",
    shortIntro: "",
    recommendReason: "",
  });

  const [feedbackForm, setFeedbackForm] = useState({
    storeName: "",
    rating: 5,
    sceneTags: [] as string[],
    tasteTags: [] as string[],
    featureTags: [] as string[],
    recommendDish: "",
    comment: "",
    warningNote: "",
  });

  const [storeSuggestions, setStoreSuggestions] = useState<string[]>([]);

  const newStoreSubmitDisabled = useMemo(() => !newStoreForm.storeName.trim() || submitting, [newStoreForm.storeName, submitting]);
  const feedbackSubmitDisabled = useMemo(
    () => !feedbackForm.storeName.trim() || !feedbackForm.comment.trim() || submitting,
    [feedbackForm.storeName, feedbackForm.comment, submitting],
  );

  useEffect(() => {
    if (mode !== "dining_feedback") return;
    const keyword = feedbackForm.storeName.trim();
    if (keyword.length < 2) {
      setStoreSuggestions([]);
      return;
    }

    let canceled = false;
    const timer = setTimeout(async () => {
      const items = await fetchStoreNameSuggestions(keyword);
      if (!canceled) {
        setStoreSuggestions(items);
      }
    }, 220);

    return () => {
      canceled = true;
      clearTimeout(timer);
    };
  }, [mode, feedbackForm.storeName]);

  const resetNotice = () => {
    setStatus("idle");
    setMessage("");
  };

  const handleSubmitNewStore = async () => {
    const payload: FeedbackPayload = {
      feedbackType: "new_store",
      storeName: newStoreForm.storeName.trim(),
      anonymousId,
      userId,
      area: newStoreForm.area.trim() || undefined,
      category: newStoreForm.category.trim() || undefined,
      avgPrice: newStoreForm.avgPrice ? Number(newStoreForm.avgPrice) : undefined,
      shortIntro: newStoreForm.shortIntro.trim() || undefined,
      recommendReason: newStoreForm.recommendReason.trim() || undefined,
      source: "frontend_user_feedback",
    };

    try {
      setSubmitting(true);
      resetNotice();
      const res = await submitFeedback(payload);
      setStatus("success");
      setMessage(res.message || "新店推荐提交成功。");
      setNewStoreForm({
        storeName: "",
        area: "",
        category: "",
        avgPrice: "",
        shortIntro: "",
        recommendReason: "",
      });
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "提交失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitDiningFeedback = async () => {
    const payload: FeedbackPayload = {
      feedbackType: "dining_feedback",
      storeName: feedbackForm.storeName.trim(),
      anonymousId,
      userId,
      rating: feedbackForm.rating,
      sceneTags: feedbackForm.sceneTags,
      tasteTags: feedbackForm.tasteTags,
      featureTags: feedbackForm.featureTags,
      recommendDish: feedbackForm.recommendDish.trim() || undefined,
      comment: feedbackForm.comment.trim(),
      warningNote: feedbackForm.warningNote.trim() || undefined,
      source: "frontend_user_feedback",
    };

    try {
      setSubmitting(true);
      resetNotice();
      const res = await submitFeedback(payload);
      setStatus("success");
      setMessage(res.message || "吃后反馈提交成功。感谢共建！");
      setFeedbackForm({
        storeName: "",
        rating: 5,
        sceneTags: [],
        tasteTags: [],
        featureTags: [],
        recommendDish: "",
        comment: "",
        warningNote: "",
      });
      setStoreSuggestions([]);
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "提交失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <aside className="feedback-panel" aria-live="polite">
      {showHeader && (
        <div className="feedback-head">
          <h2>校园美食共创</h2>
          <p>你的一次反馈，会让下一位同学吃得更好。</p>
        </div>
      )}

      <div className="feedback-tabs" role="tablist" aria-label="反馈类型">
        <button
          type="button"
          className={`feedback-tab ${mode === "new_store" ? "active" : ""}`}
          onClick={() => {
            setMode("new_store");
            resetNotice();
          }}
          role="tab"
          aria-selected={mode === "new_store"}
        >
          推荐新店
        </button>
        <button
          type="button"
          className={`feedback-tab ${mode === "dining_feedback" ? "active" : ""}`}
          onClick={() => {
            setMode("dining_feedback");
            resetNotice();
          }}
          role="tab"
          aria-selected={mode === "dining_feedback"}
        >
          吃后反馈
        </button>
      </div>

      {mode === "new_store" ? (
        <div className="feedback-body" key="new_store">
          <label>
            店名 *
            <input
              value={newStoreForm.storeName}
              onChange={(e) => setNewStoreForm((prev) => ({ ...prev, storeName: e.target.value }))}
              placeholder="例如：南门砂锅王"
            />
          </label>
          <div className="feedback-grid-2">
            <label>
              区域
              <input value={newStoreForm.area} onChange={(e) => setNewStoreForm((prev) => ({ ...prev, area: e.target.value }))} placeholder="西门 / 南门 / 校外" />
            </label>
            <label>
              类别
              <input value={newStoreForm.category} onChange={(e) => setNewStoreForm((prev) => ({ ...prev, category: e.target.value }))} placeholder="面馆 / 盖饭 / 冒菜" />
            </label>
          </div>
          <label>
            人均价格
            <input
              type="number"
              min={0}
              max={500}
              value={newStoreForm.avgPrice}
              onChange={(e) => setNewStoreForm((prev) => ({ ...prev, avgPrice: e.target.value }))}
              placeholder="例如：25"
            />
          </label>
          <label>
            新店简介
            <textarea value={newStoreForm.shortIntro} onChange={(e) => setNewStoreForm((prev) => ({ ...prev, shortIntro: e.target.value }))} rows={2} placeholder="一句话介绍新店亮点" />
          </label>
          <label>
            推荐理由
            <textarea
              value={newStoreForm.recommendReason}
              onChange={(e) => setNewStoreForm((prev) => ({ ...prev, recommendReason: e.target.value }))}
              rows={2}
              placeholder="为什么值得推荐给同学？"
            />
          </label>
          <button type="button" className="feedback-submit" onClick={() => void handleSubmitNewStore()} disabled={newStoreSubmitDisabled}>
            {submitting ? "提交中..." : "提交新店推荐"}
          </button>
        </div>
      ) : (
        <div className="feedback-body" key="dining_feedback">
          <label>
            店名 *
            <input
              value={feedbackForm.storeName}
              onChange={(e) => setFeedbackForm((prev) => ({ ...prev, storeName: e.target.value }))}
              placeholder="例如：李四面馆"
              list="feedback-store-suggestions"
            />
            <datalist id="feedback-store-suggestions">
              {storeSuggestions.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </label>

          <label>
            评分 *
            <select
              value={feedbackForm.rating}
              onChange={(e) => setFeedbackForm((prev) => ({ ...prev, rating: Number(e.target.value) }))}
            >
              {[5, 4, 3, 2, 1].map((n) => (
                <option value={n} key={n}>
                  {n} 分
                </option>
              ))}
            </select>
          </label>

          <div className="feedback-tag-group">
            <span>场景标签</span>
            <div className="feedback-tag-list">
              {SCENE_OPTIONS.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  className={`feedback-tag ${feedbackForm.sceneTags.includes(tag) ? "active" : ""}`}
                  onClick={() => setFeedbackForm((prev) => ({ ...prev, sceneTags: toggleTag(prev.sceneTags, tag) }))}
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>

          <div className="feedback-tag-group">
            <span>口味标签</span>
            <div className="feedback-tag-list">
              {TASTE_OPTIONS.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  className={`feedback-tag ${feedbackForm.tasteTags.includes(tag) ? "active" : ""}`}
                  onClick={() => setFeedbackForm((prev) => ({ ...prev, tasteTags: toggleTag(prev.tasteTags, tag) }))}
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>

          <div className="feedback-tag-group">
            <span>特色标签</span>
            <div className="feedback-tag-list">
              {FEATURE_OPTIONS.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  className={`feedback-tag ${feedbackForm.featureTags.includes(tag) ? "active" : ""}`}
                  onClick={() => setFeedbackForm((prev) => ({ ...prev, featureTags: toggleTag(prev.featureTags, tag) }))}
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>

          <label>
            推荐菜
            <input
              value={feedbackForm.recommendDish}
              onChange={(e) => setFeedbackForm((prev) => ({ ...prev, recommendDish: e.target.value }))}
              placeholder="例如：番茄牛肉面"
            />
          </label>
          <label>
            用餐评论 *
            <textarea value={feedbackForm.comment} onChange={(e) => setFeedbackForm((prev) => ({ ...prev, comment: e.target.value }))} rows={3} placeholder="说说你真实的用餐体验" />
          </label>
          <label>
            可能提醒
            <textarea
              value={feedbackForm.warningNote}
              onChange={(e) => setFeedbackForm((prev) => ({ ...prev, warningNote: e.target.value }))}
              rows={2}
              placeholder="例如：高峰期排队久"
            />
          </label>
          <button type="button" className="feedback-submit" onClick={() => void handleSubmitDiningFeedback()} disabled={feedbackSubmitDisabled}>
            {submitting ? "提交中..." : "提交吃后反馈"}
          </button>
        </div>
      )}

      {status !== "idle" && (
        <div className={`feedback-status ${status === "success" ? "success" : "error"}`}>
          {message}
        </div>
      )}
    </aside>
  );
}
