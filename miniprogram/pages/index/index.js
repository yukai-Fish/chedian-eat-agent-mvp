const { fetchRecommendations, submitFeedback, API_BASE_URL } = require("../../utils/api");
const { getCurrentIdentity } = require("../../utils/identity");
const { parseRecommendationAnswer } = require("../../utils/recommendation");

const QUICK_PROMPTS = [
  "清水河附近，预算 25，一个人，想吃清淡一点",
  "沙河校区，晚上和室友聚餐，预算 35，想吃辣",
  "现在在清水河，夜宵有什么性价比高的推荐？",
];

function getVisibleCards(cards, batchSize, batchIndex) {
  if (!Array.isArray(cards) || cards.length === 0) return [];
  const size = Math.max(1, Number(batchSize) || 3);
  const groupCount = Math.max(1, Math.ceil(cards.length / size));
  const start = (batchIndex % groupCount) * size;
  return cards.slice(start, start + size);
}

Page({
  data: {
    apiBaseUrl: API_BASE_URL,
    identityLabel: "匿名使用",
    query: "",
    loading: false,
    error: "",
    summary: "输入你的需求，获取校园美食推荐。",
    cards: [],
    visibleCards: [],
    currentBatchIndex: 0,
    batchSize: 3,
    canSwitchBatch: false,
    rawAnswer: "",
    quickPrompts: QUICK_PROMPTS,
    feedbackOpen: false,
    feedbackTab: "new_store",
    feedbackLoading: false,
    feedbackForm: {
      storeName: "",
      comment: "",
      rating: 5,
      recommendDish: "",
      recommendReason: "",
    },
  },

  onLoad() {
    const identity = getCurrentIdentity();
    this.identity = identity;
    this.setData({
      identityLabel: identity.kind === "authenticated" ? "已登录" : `匿名：${identity.anonymousId.slice(-6)}`,
      query: QUICK_PROMPTS[0],
    });
  },

  onInputQuery(e) {
    this.setData({ query: e.detail.value || "" });
  },

  onTapQuickPrompt(e) {
    const text = e.currentTarget.dataset.prompt || "";
    this.setData({ query: text });
  },

  async onSubmitQuery() {
    const query = (this.data.query || "").trim();
    if (!query || this.data.loading) return;

    this.setData({
      loading: true,
      error: "",
    });

    try {
      const result = await fetchRecommendations({
        query,
        anonymousId: this.identity.anonymousId,
        userId: this.identity.userId || undefined,
        uid: this.identity.uid,
        history: [],
      });

      if (!result.ok) {
        this.setData({
          error: result.error || "推荐请求失败，请稍后再试。",
          loading: false,
          cards: [],
          visibleCards: [],
          summary: "暂未获得推荐结果。",
          rawAnswer: "",
          canSwitchBatch: false,
        });
        return;
      }

      const parsed = parseRecommendationAnswer(result.answer || "");
      const cards = parsed.cards || [];
      const visibleCards = getVisibleCards(cards, parsed.batchSize, 0);
      const canSwitchBatch = cards.length > Math.max(1, parsed.batchSize || 3);

      this.setData({
        loading: false,
        cards,
        visibleCards,
        currentBatchIndex: 0,
        batchSize: parsed.batchSize || 3,
        summary: parsed.summary,
        rawAnswer: parsed.rawAnswer || "",
        canSwitchBatch,
      });
    } catch (err) {
      this.setData({
        loading: false,
        error: err && err.message ? err.message : "网络异常，请检查后重试。",
      });
    }
  },

  onSwitchBatch() {
    const cards = this.data.cards || [];
    const size = Math.max(1, Number(this.data.batchSize) || 3);
    const groupCount = Math.max(1, Math.ceil(cards.length / size));
    const nextIndex = (this.data.currentBatchIndex + 1) % groupCount;
    const visibleCards = getVisibleCards(cards, size, nextIndex);
    this.setData({
      currentBatchIndex: nextIndex,
      visibleCards,
    });
  },

  openFeedback() {
    this.setData({ feedbackOpen: true });
  },

  closeFeedback() {
    this.setData({ feedbackOpen: false });
  },

  onTapFeedbackMask() {
    this.closeFeedback();
  },

  stopTap() {},

  onSwitchFeedbackTab(e) {
    const tab = e.currentTarget.dataset.tab;
    if (!tab) return;
    this.setData({ feedbackTab: tab });
  },

  onFeedbackFieldInput(e) {
    const field = e.currentTarget.dataset.field;
    if (!field) return;
    this.setData({
      [`feedbackForm.${field}`]: e.detail.value || "",
    });
  },

  onFeedbackRatingChange(e) {
    this.setData({
      "feedbackForm.rating": Number(e.detail.value) || 5,
    });
  },

  async onSubmitFeedback() {
    if (this.data.feedbackLoading) return;
    const form = this.data.feedbackForm || {};
    const storeName = (form.storeName || "").trim();
    if (!storeName) {
      wx.showToast({ title: "请填写店名", icon: "none" });
      return;
    }

    const isDining = this.data.feedbackTab === "dining_feedback";
    const payload = {
      feedbackType: this.data.feedbackTab,
      storeName,
      anonymousId: this.identity.anonymousId,
      userId: this.identity.userId || undefined,
      source: "miniprogram",
      comment: (form.comment || "").trim() || undefined,
      recommendDish: (form.recommendDish || "").trim() || undefined,
      recommendReason: (form.recommendReason || "").trim() || undefined,
      rating: isDining ? Number(form.rating) || 5 : undefined,
    };

    if (isDining && !payload.comment) {
      wx.showToast({ title: "吃后反馈请填写评论", icon: "none" });
      return;
    }

    this.setData({ feedbackLoading: true });
    try {
      await submitFeedback(payload);
      wx.showToast({ title: "反馈已提交", icon: "success" });
      this.setData({
        feedbackLoading: false,
        feedbackOpen: false,
        feedbackForm: {
          storeName: "",
          comment: "",
          rating: 5,
          recommendDish: "",
          recommendReason: "",
        },
      });
    } catch (err) {
      this.setData({ feedbackLoading: false });
      wx.showToast({
        title: err && err.message ? err.message : "提交失败，请稍后重试",
        icon: "none",
      });
    }
  },
});
