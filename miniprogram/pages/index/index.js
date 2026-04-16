const { fetchRecommendations, submitFeedback, fetchStoreDetail, fetchTodayRankings, logRankingClick, API_BASE_URL } = require("../../utils/api");
const { getCurrentIdentity } = require("../../utils/identity");
const { parseRecommendationAnswer } = require("../../utils/recommendation");

const QUICK_PROMPTS = [
  "清水河附近，预算 25，一个人，想吃清淡一点",
  "沙河校区，晚上和室友聚餐，预算 35，想吃辣",
  "现在在清水河，夜宵有什么性价比高的推荐？",
];
const MAX_DISLIKED = 8;
const FOLLOW_UP_PRESETS = [
  { key: "cheaper", label: "更便宜", prompt: "预算再低一些，优先人均更低的店" },
  { key: "spicier", label: "更辣", prompt: "口味更偏辣，优先重口和香辣" },
  { key: "nearby", label: "离我更近", prompt: "优先离当前校区更近、步行更方便的店" },
  { key: "solo", label: "适合一个人", prompt: "优先适合一个人吃、出餐快的店" },
];
const MAX_HISTORY = 8;
const MAX_FAVORITES = 50;

function getVisibleCards(cards, batchSize, batchIndex) {
  if (!Array.isArray(cards) || cards.length === 0) return [];
  const size = Math.max(1, Number(batchSize) || 3);
  const groupCount = Math.max(1, Math.ceil(cards.length / size));
  const start = (batchIndex % groupCount) * size;
  return cards.slice(start, start + size);
}

function filterDisliked(cards, dislikedNames) {
  if (!Array.isArray(cards) || cards.length === 0) return [];
  if (!Array.isArray(dislikedNames) || dislikedNames.length === 0) return cards.slice();
  const excluded = new Set(dislikedNames);
  return cards.filter((card) => card && !excluded.has(card.name));
}

function buildRefinedQuery(query, dislikedNames) {
  const base = String(query || "").trim();
  const names = (Array.isArray(dislikedNames) ? dislikedNames : []).slice(0, MAX_DISLIKED);
  const excludeHint = names.length ? `，不要推荐：${names.join("、")}` : "";
  return `${base}。换个口味，尽量和上一批不同${excludeHint}。`;
}

function pickCardNames(cards) {
  return (Array.isArray(cards) ? cards : [])
    .map((card) => String((card && card.name) || "").trim())
    .filter(Boolean);
}

function mergeDislikedNames(...nameLists) {
  const seen = new Set();
  const merged = [];
  nameLists.forEach((list) => {
    (Array.isArray(list) ? list : []).forEach((name) => {
      const key = String(name || "").trim();
      if (!key || seen.has(key)) return;
      seen.add(key);
      merged.push(key);
    });
  });
  return merged.slice(-MAX_DISLIKED);
}

function parseIntervals(openHoursText) {
  const text = String(openHoursText || "").trim();
  if (!text || text === "无") return { unknown: true, allDay: false, intervals: [] };
  if (text.includes("全天") || text.includes("24:00-24:00")) {
    return { unknown: false, allDay: true, intervals: [[0, 24 * 60]] };
  }
  const matches = [...text.matchAll(/(\d{1,2})[:：](\d{1,2})/g)];
  if (matches.length < 2) return { unknown: true, allDay: false, intervals: [] };

  const points = matches
    .map((m) => [Number(m[1]), Number(m[2])])
    .filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]) && p[0] >= 0 && p[0] <= 26 && p[1] >= 0 && p[1] <= 59)
    .map((p) => p[0] * 60 + p[1]);

  const intervals = [];
  for (let i = 0; i + 1 < points.length; i += 2) {
    let start = points[i];
    let end = points[i + 1];
    if (end <= start) end += 24 * 60;
    intervals.push([start, end]);
  }
  return { unknown: intervals.length === 0, allDay: false, intervals };
}

function isOpenNow(openHoursText) {
  const parsed = parseIntervals(openHoursText);
  if (parsed.unknown) return null;
  if (parsed.allDay) return true;

  const now = new Date();
  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  for (const [start, end] of parsed.intervals) {
    if ((nowMinutes >= start && nowMinutes < end) || (nowMinutes + 24 * 60 >= start && nowMinutes + 24 * 60 < end)) {
      return true;
    }
  }
  return false;
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
    onlyOpenNow: false,
    cardOpenStatus: {},
    dislikedNames: [],
    followUps: FOLLOW_UP_PRESETS,
    rawAnswer: "",
    quickPrompts: QUICK_PROMPTS,
    rankingsLoading: false,
    rankingsError: "",
    rankingsUpdatedAt: "",
    rankings: [],
    favorites: [],
    queryHistory: [],
    feedbackOpen: false,
    feedbackTab: "new_store",
    feedbackLoading: false,
    quickDiningOpen: false,
    quickDiningLoading: false,
    quickDiningForm: {
      storeName: "",
      rating: 5,
      comment: "",
    },
    feedbackForm: {
      storeName: "",
      comment: "",
      rating: 5,
      recommendDish: "",
      recommendReason: "",
    },
  },

  getDisplayCards(cards, cardOpenStatus, onlyOpenNow) {
    const baseCards = Array.isArray(cards) ? cards : [];
    if (!onlyOpenNow) return baseCards;
    const statusMap = cardOpenStatus || {};
    return baseCards.filter((card) => statusMap[card.name] === true);
  },

  syncVisibleCards(options = {}) {
    const cards = Array.isArray(options.cards) ? options.cards : this.data.cards || [];
    const batchSize = Math.max(1, Number(options.batchSize || this.data.batchSize) || 3);
    const cardOpenStatus = options.cardOpenStatus || this.data.cardOpenStatus || {};
    const onlyOpenNow = typeof options.onlyOpenNow === "boolean" ? options.onlyOpenNow : !!this.data.onlyOpenNow;
    const displayCards = this.getDisplayCards(cards, cardOpenStatus, onlyOpenNow);
    const groupCount = Math.max(1, Math.ceil(displayCards.length / batchSize));
    const sourceIndex = Number.isFinite(options.currentBatchIndex)
      ? options.currentBatchIndex
      : (Number(this.data.currentBatchIndex) || 0);
    const currentBatchIndex = displayCards.length === 0 ? 0 : sourceIndex % groupCount;
    const visibleCards = getVisibleCards(displayCards, batchSize, currentBatchIndex);
    const canSwitchBatch = displayCards.length > batchSize;

    this.setData({
      cards,
      batchSize,
      currentBatchIndex,
      visibleCards,
      canSwitchBatch,
      onlyOpenNow,
    });
  },

  async ensureCardOpenStatus(cards) {
    const list = Array.isArray(cards) ? cards : [];
    if (!list.length) return;
    const existing = this.data.cardOpenStatus || {};
    const targets = list
      .map((card) => (card && card.name ? String(card.name).trim() : ""))
      .filter((name) => name && !(name in existing));
    if (!targets.length) return;

    const updates = {};
    await Promise.all(
      targets.map(async (name) => {
        try {
          const res = await fetchStoreDetail(name);
          if (!res || !res.found || !res.store) {
            updates[name] = null;
            return;
          }
          updates[name] = isOpenNow(res.store.openHours);
        } catch (_err) {
          updates[name] = null;
        }
      })
    );

    const nextStatus = Object.assign({}, this.data.cardOpenStatus || {}, updates);
    this.setData({ cardOpenStatus: nextStatus });
    this.syncVisibleCards({ cardOpenStatus: nextStatus });
  },

  onLoad() {
    const identity = getCurrentIdentity();
    this.identity = identity;
    this.setData({
      identityLabel: identity.kind === "authenticated" ? "已登录" : `匿名：${identity.anonymousId.slice(-6)}`,
      query: QUICK_PROMPTS[0],
    });
    this.loadLocalUserData();
    this.loadTodayRankings();
  },

  getStorageKeys() {
    const anon = this.identity && this.identity.anonymousId ? this.identity.anonymousId : "anonymous";
    return {
      favoritesKey: `chedian.minip.favorites.${anon}`,
      historyKey: `chedian.minip.history.${anon}`,
    };
  },

  loadLocalUserData() {
    const keys = this.getStorageKeys();
    const favorites = wx.getStorageSync(keys.favoritesKey);
    const queryHistory = wx.getStorageSync(keys.historyKey);
    this.setData({
      favorites: Array.isArray(favorites) ? favorites.slice(0, MAX_FAVORITES) : [],
      queryHistory: Array.isArray(queryHistory) ? queryHistory.slice(0, MAX_HISTORY) : [],
    });
  },

  saveFavorites(nextFavorites) {
    const keys = this.getStorageKeys();
    const value = Array.isArray(nextFavorites) ? nextFavorites.slice(0, MAX_FAVORITES) : [];
    wx.setStorageSync(keys.favoritesKey, value);
    this.setData({ favorites: value });
  },

  saveQueryHistory(nextHistory) {
    const keys = this.getStorageKeys();
    const value = Array.isArray(nextHistory) ? nextHistory.slice(0, MAX_HISTORY) : [];
    wx.setStorageSync(keys.historyKey, value);
    this.setData({ queryHistory: value });
  },

  markQueryHistory(query) {
    const text = String(query || "").trim();
    if (!text) return;
    const current = this.data.queryHistory || [];
    const next = [text].concat(current.filter((item) => item !== text)).slice(0, MAX_HISTORY);
    this.saveQueryHistory(next);
  },

  isFavorite(name) {
    const key = String(name || "").trim();
    if (!key) return false;
    return (this.data.favorites || []).includes(key);
  },

  async loadTodayRankings() {
    if (this.data.rankingsLoading) return;
    this.setData({
      rankingsLoading: true,
      rankingsError: "",
    });
    try {
      const res = await fetchTodayRankings();
      const items = Array.isArray(res.items) ? res.items : [];
      this.setData({
        rankingsLoading: false,
        rankings: items.slice(0, 5),
        rankingsUpdatedAt: res.updated_at || "",
      });
    } catch (err) {
      const message = (err && err.message) || "";
      const hint = message.includes("HTTP 5")
        ? "热度榜服务暂时开小差了，点重试再试一次"
        : "热度榜加载失败，请稍后重试";
      this.setData({
        rankingsLoading: false,
        rankingsError: hint,
      });
    }
  },

  onRetryRankings() {
    this.loadTodayRankings();
  },

  async runRecommendation(query, options = {}) {
    const resetDisliked = !!options.resetDisliked;
    const forceRefine = !!options.forceRefine;
    const cleanQuery = String(query || "").trim();
    if (!cleanQuery || this.data.loading) return false;

    if (resetDisliked && this.data.dislikedNames.length) {
      this.setData({ dislikedNames: [] });
    }

    const dislikedNames = Array.isArray(options.dislikedNames) ? options.dislikedNames : (this.data.dislikedNames || []);
    const requestQuery = forceRefine ? buildRefinedQuery(cleanQuery, dislikedNames) : cleanQuery;

    this.setData({
      loading: true,
      error: "",
    });

    try {
      const result = await fetchRecommendations({
        query: requestQuery,
        anonymousId: this.identity.anonymousId,
        userId: this.identity.userId || undefined,
        uid: this.identity.uid,
        excludeStoreNames: dislikedNames,
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
        return false;
      }

      const parsed = parseRecommendationAnswer(result.answer || "");
      const rawCards = parsed.cards || [];
      const cards = filterDisliked(rawCards, dislikedNames);
      const summarySuffix = forceRefine ? "（已按你的反馈换口味）" : "";

      this.setData({
        loading: false,
        summary: `${parsed.summary || "已为你生成新推荐。"}${summarySuffix}`,
        rawAnswer: parsed.rawAnswer || "",
      });
      this.markQueryHistory(cleanQuery);
      this.syncVisibleCards({
        cards,
        batchSize: parsed.batchSize || 3,
        currentBatchIndex: 0,
      });
      this.ensureCardOpenStatus(cards);
      return true;
    } catch (err) {
      this.setData({
        loading: false,
        error: err && err.message ? err.message : "网络异常，请检查后重试。",
      });
      return false;
    }
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
    await this.runRecommendation(query, { resetDisliked: true });
  },

  onSwitchBatch() {
    const cards = this.getDisplayCards(this.data.cards || [], this.data.cardOpenStatus || {}, this.data.onlyOpenNow);
    const size = Math.max(1, Number(this.data.batchSize) || 3);
    const groupCount = Math.max(1, Math.ceil(cards.length / size));
    const nextIndex = (this.data.currentBatchIndex + 1) % groupCount;
    const visibleCards = getVisibleCards(cards, size, nextIndex);
    this.setData({
      currentBatchIndex: nextIndex,
      visibleCards,
    });
  },

  onOpenStoreDetail(e) {
    const storeName = (e.currentTarget.dataset.name || "").trim();
    if (!storeName) return;
    wx.navigateTo({
      url: `/pages/store-detail/index?name=${encodeURIComponent(storeName)}`,
    });
  },

  onToggleFavorite(e) {
    const name = (e.currentTarget.dataset.name || "").trim();
    if (!name) return;
    const current = this.data.favorites || [];
    const exists = current.includes(name);
    const next = exists ? current.filter((item) => item !== name) : [name].concat(current).slice(0, MAX_FAVORITES);
    this.saveFavorites(next);
    wx.showToast({ title: exists ? "已取消收藏" : "已收藏", icon: "none" });
  },

  onTapHistoryQuery(e) {
    const text = (e.currentTarget.dataset.query || "").trim();
    if (!text) return;
    this.setData({ query: text });
    this.runRecommendation(text);
  },

  onTapFavoriteItem(e) {
    const name = (e.currentTarget.dataset.name || "").trim();
    if (!name) return;
    wx.navigateTo({
      url: `/pages/store-detail/index?name=${encodeURIComponent(name)}`,
    });
  },

  async onRefineTaste() {
    const query = (this.data.query || "").trim();
    if (!query || this.data.loading) return;
    const previousVisible = pickCardNames(this.data.visibleCards);
    const nextDisliked = mergeDislikedNames(this.data.dislikedNames, previousVisible);
    this.setData({ dislikedNames: nextDisliked });

    const ok = await this.runRecommendation(query, {
      forceRefine: true,
      dislikedNames: nextDisliked,
    });

    if (!ok) return;

    const currentVisible = pickCardNames(this.data.visibleCards);
    const overlap = currentVisible.filter((name) => previousVisible.includes(name));
    if (overlap.length > 0 && currentVisible.length > 0) {
      wx.showToast({ title: "已尽量换口味，可再点一次继续换", icon: "none" });
    }
  },

  async onTapFollowUp(e) {
    const key = e.currentTarget.dataset.key;
    const followUps = this.data.followUps || [];
    const chosen = followUps.find((item) => item.key === key);
    if (!chosen || this.data.loading) return;

    const base = (this.data.query || "").trim();
    if (!base) return;
    const nextQuery = `${base}。${chosen.prompt}。`;
    this.setData({ query: nextQuery });
    await this.runRecommendation(nextQuery);
  },

  async onTapRankingItem(e) {
    const name = (e.currentTarget.dataset.name || "").trim();
    const shopId = (e.currentTarget.dataset.shopId || "").trim();
    if (!name) return;

    try {
      await logRankingClick({
        shop_id: shopId || `name:${name}`,
        shop_name: name,
        uid: this.identity.uid,
        anonymousId: this.identity.anonymousId,
        userId: this.identity.userId || undefined,
      });
    } catch (_err) {
      // best-effort analytics
    }

    wx.navigateTo({
      url: `/pages/store-detail/index?name=${encodeURIComponent(name)}`,
    });
  },

  onToggleOnlyOpenNow() {
    if (this.data.loading) return;
    const next = !this.data.onlyOpenNow;
    this.syncVisibleCards({ onlyOpenNow: next, currentBatchIndex: 0 });
    if (next) {
      this.ensureCardOpenStatus(this.data.cards || []);
      wx.showToast({ title: "已切换为只看营业中", icon: "none" });
      return;
    }
    wx.showToast({ title: "已显示全部推荐", icon: "none" });
  },

  async onDislikeCard(e) {
    const name = (e.currentTarget.dataset.name || "").trim();
    if (!name || this.data.loading) return;

    const dislikedNames = this.data.dislikedNames || [];
    if (dislikedNames.includes(name)) return;
    const nextDisliked = dislikedNames.concat(name).slice(-MAX_DISLIKED);
    const filteredCards = filterDisliked(this.data.cards || [], nextDisliked);

    if (filteredCards.length > 0) {
      this.syncVisibleCards({
        cards: filteredCards,
        currentBatchIndex: 0,
      });
      this.setData({
        dislikedNames: nextDisliked,
      });
      this.ensureCardOpenStatus(filteredCards);
      wx.showToast({ title: "已为你换一批", icon: "none" });
      return;
    }

    this.setData({ dislikedNames: nextDisliked });
    wx.showToast({ title: "正在按偏好重算", icon: "none" });
    await this.onRefineTaste();
  },

  onClearDisliked() {
    if (this.data.loading) return;
    this.setData({ dislikedNames: [] });
    wx.showToast({ title: "已清除排除项", icon: "none" });
  },

  openQuickDining(e) {
    const storeName = (e.currentTarget.dataset.name || "").trim();
    if (!storeName || this.data.loading) return;
    this.setData({
      quickDiningOpen: true,
      quickDiningLoading: false,
      quickDiningForm: {
        storeName,
        rating: 5,
        comment: "",
      },
    });
  },

  closeQuickDining() {
    this.setData({
      quickDiningOpen: false,
      quickDiningLoading: false,
    });
  },

  onQuickDiningRatingChange(e) {
    this.setData({
      "quickDiningForm.rating": Number(e.detail.value) || 5,
    });
  },

  onQuickDiningCommentInput(e) {
    this.setData({
      "quickDiningForm.comment": e.detail.value || "",
    });
  },

  async onSubmitQuickDining() {
    if (this.data.quickDiningLoading) return;
    const form = this.data.quickDiningForm || {};
    const storeName = String(form.storeName || "").trim();
    const comment = String(form.comment || "").trim();
    if (!storeName) return;
    if (!comment) {
      wx.showToast({ title: "请写一句用餐评价", icon: "none" });
      return;
    }

    const payload = {
      feedbackType: "dining_feedback",
      storeName,
      anonymousId: this.identity.anonymousId,
      userId: this.identity.userId || undefined,
      source: "miniprogram_quick_dining",
      rating: Number(form.rating) || 5,
      comment,
    };

    this.setData({ quickDiningLoading: true });
    try {
      await submitFeedback(payload);
      wx.showToast({ title: "已记录你的反馈", icon: "success" });
      this.setData({
        quickDiningOpen: false,
        quickDiningLoading: false,
        quickDiningForm: {
          storeName: "",
          rating: 5,
          comment: "",
        },
      });
    } catch (err) {
      this.setData({ quickDiningLoading: false });
      wx.showToast({
        title: err && err.message ? err.message : "提交失败，请稍后重试",
        icon: "none",
      });
    }
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
