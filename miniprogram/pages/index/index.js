const {
  fetchRecommendations,
  submitFeedback,
  fetchStoreDetail,
  fetchTodayRankings,
  logRankingClick,
  fetchProfileData,
  addFavorite,
  removeFavorite,
  API_BASE_URL,
} = require("../../utils/api");
const { getCurrentIdentity } = require("../../utils/identity");
const { trackEvent } = require("../../utils/analytics");
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
const CAMPUS_CENTERS = {
  "清水河": { latitude: 30.7522, longitude: 103.9349 },
  "沙河": { latitude: 30.6742, longitude: 104.1003 },
};
const CAMPUS_AREA_ANCHORS = {
  "清水河": [
    { areaHint: "校内", latitude: 30.7522, longitude: 103.9349 },
    { areaHint: "西门", latitude: 30.7522, longitude: 103.9259 },
    { areaHint: "南门", latitude: 30.7452, longitude: 103.9349 },
  ],
  "沙河": [
    { areaHint: "校内", latitude: 30.6742, longitude: 104.1003 },
    { areaHint: "西门", latitude: 30.6742, longitude: 104.0945 },
    { areaHint: "南门", latitude: 30.6697, longitude: 104.1003 },
  ],
};

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

function mergeUniqueStrings(...lists) {
  const seen = new Set();
  const merged = [];
  lists.forEach((list) => {
    (Array.isArray(list) ? list : []).forEach((item) => {
      const text = String(item || "").trim();
      if (!text || seen.has(text)) return;
      seen.add(text);
      merged.push(text);
    });
  });
  return merged;
}

function toRadians(deg) {
  return (Number(deg) * Math.PI) / 180;
}

function distanceKm(lat1, lng1, lat2, lng2) {
  const r = 6371.0088;
  const dLat = toRadians(lat2 - lat1);
  const dLng = toRadians(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * r * Math.asin(Math.min(1, Math.sqrt(a)));
}

function inferCampusContext(latitude, longitude) {
  let bestCampus = "";
  let bestCampusDistance = Number.POSITIVE_INFINITY;
  Object.keys(CAMPUS_CENTERS).forEach((campus) => {
    const point = CAMPUS_CENTERS[campus];
    const km = distanceKm(latitude, longitude, point.latitude, point.longitude);
    if (km < bestCampusDistance) {
      bestCampus = campus;
      bestCampusDistance = km;
    }
  });

  if (!bestCampus) return null;

  const anchors = CAMPUS_AREA_ANCHORS[bestCampus] || [];
  let bestArea = "鏍″唴";
  let bestAreaDistance = Number.POSITIVE_INFINITY;
  anchors.forEach((anchor) => {
    const km = distanceKm(latitude, longitude, anchor.latitude, anchor.longitude);
    if (km < bestAreaDistance) {
      bestArea = anchor.areaHint;
      bestAreaDistance = km;
    }
  });

  return {
    campus: bestCampus,
    campusDistanceKm: Number(bestCampusDistance.toFixed(2)),
    areaHint: bestArea,
    areaDistanceKm: Number.isFinite(bestAreaDistance) ? Number(bestAreaDistance.toFixed(2)) : null,
  };
}

function buildNearbyHintText(locationContext) {
  if (!locationContext || !locationContext.campus) return "";
  const areaText = locationContext.areaHint ? `${locationContext.areaHint}附近` : "";
  return `我当前在${locationContext.campus}${areaText}，优先同校区、步行更近且当下可去的店。`;
}

function parseIntervals(openHoursText) {
  const text = String(openHoursText || "").trim();
  if (!text || text === "无") return { unknown: true, allDay: false, intervals: [] };
  if (text.includes("鍏ㄥぉ") || text.includes("24:00-24:00")) {
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
    preferNearby: false,
    locationLoading: false,
    locationError: "",
    locationLabel: "未定位",
    locationContext: null,
    showRankings: false,
    rankingsLoading: false,
    rankingsReady: false,
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
      query: QUICK_PROMPTS[0],
    });
    this.loadUserData();
    this.consumeAndRunExternalQuery();
  },

  onShow() {
    const latest = getCurrentIdentity();
    if (!this.identity || latest.uid !== this.identity.uid) {
      this.identity = latest;
    }
    this.loadUserData();
    this.consumeAndRunExternalQuery();
  },

  buildQueryFromExternalIntent() {
    const pendingRaw = wx.getStorageSync("chedian.minip.pendingQuery");
    const previewRaw = wx.getStorageSync("chedian.minip.pendingQueryPreview");
    const quickRaw = wx.getStorageSync("chedian.minip.quickCondition");
    const pendingQuery = String(pendingRaw || "").trim();
    const previewQuery = String(previewRaw || "").trim();
    const quickCondition = String(quickRaw || "").trim();
    if (!pendingQuery && !previewQuery && !quickCondition) return null;

    wx.removeStorageSync("chedian.minip.pendingQuery");
    wx.removeStorageSync("chedian.minip.pendingQueryPreview");
    wx.removeStorageSync("chedian.minip.quickCondition");

    const base = pendingQuery || previewQuery || String(this.data.query || "").trim() || QUICK_PROMPTS[0];
    const query = quickCondition ? `${base}。${quickCondition}` : base;
    return {
      query,
      shouldRun: !!pendingQuery || !!quickCondition,
    };
  },

  async consumeAndRunExternalQuery() {
    const intent = this.buildQueryFromExternalIntent();
    if (!intent || !intent.query) return;
    this.setData({ query: intent.query });
    if (!intent.shouldRun) return;
    await this.runRecommendation(intent.query, { resetDisliked: true });
  },

  formatLocationLabel(locationContext) {
    if (!locationContext || !locationContext.campus) return "未定位";
    const areaText = locationContext.areaHint ? `${locationContext.areaHint}附近` : "附近";
    return `${locationContext.campus}${areaText}`;
  },

  async ensureLocationContext(forceRefresh = false) {
    if (!forceRefresh && this.data.locationContext) return this.data.locationContext;
    if (this.data.locationLoading) return null;

    this.setData({ locationLoading: true, locationError: "" });
    return new Promise((resolve) => {
      wx.getLocation({
        type: "gcj02",
        isHighAccuracy: true,
        success: (res) => {
          const latitude = Number(res.latitude);
          const longitude = Number(res.longitude);
          if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
            this.setData({
              locationLoading: false,
              locationError: "定位结果异常，请重试。",
            });
            resolve(null);
            return;
          }

          const inferred = inferCampusContext(latitude, longitude) || {};
          const nextContext = {
            latitude,
            longitude,
            accuracy: Number(res.accuracy) || null,
            campus: inferred.campus || "",
            areaHint: inferred.areaHint || "",
            campusDistanceKm: inferred.campusDistanceKm || null,
            areaDistanceKm: inferred.areaDistanceKm || null,
          };
          this.setData({
            locationLoading: false,
            locationError: "",
            locationContext: nextContext,
            locationLabel: this.formatLocationLabel(nextContext),
          });
          resolve(nextContext);
        },
        fail: (err) => {
          const msg = String((err && err.errMsg) || "");
          const denied = msg.includes("auth deny") || msg.includes("auth denied");
          this.setData({
            locationLoading: false,
            locationError: denied ? "定位权限未开启，请在设置中允许定位。" : "定位失败，请稍后重试。",
          });
          if (denied) {
            wx.showModal({
              title: "需要定位权限",
              content: "开启后可优先推荐你附近可步行到达的店铺。",
              confirmText: "去设置",
              success: (modalRes) => {
                if (!modalRes.confirm) return;
                wx.openSetting({});
              },
            });
          }
          resolve(null);
        },
      });
    });
  },

  getStorageKeys() {
    const anon = this.identity && this.identity.anonymousId ? this.identity.anonymousId : "anonymous";
    return {
      favoritesKey: `chedian.minip.favorites.${anon}`,
      historyKey: `chedian.minip.history.${anon}`,
    };
  },

  readLocalUserData() {
    const keys = this.getStorageKeys();
    const favorites = wx.getStorageSync(keys.favoritesKey);
    const queryHistory = wx.getStorageSync(keys.historyKey);
    return {
      favorites: Array.isArray(favorites) ? favorites.slice(0, MAX_FAVORITES) : [],
      queryHistory: Array.isArray(queryHistory) ? queryHistory.slice(0, MAX_HISTORY) : [],
    };
  },

  async loadUserData() {
    const local = this.readLocalUserData();
    let favorites = local.favorites;
    let queryHistory = local.queryHistory;

    if (this.identity && this.identity.userId) {
      try {
        const remote = await fetchProfileData(this.identity.userId);
        const remoteFavorites = Array.isArray(remote && remote.favorites) ? remote.favorites : [];
        const remoteHistory = Array.isArray(remote && remote.queryHistory) ? remote.queryHistory : [];
        favorites = mergeUniqueStrings(remoteFavorites, favorites).slice(0, MAX_FAVORITES);
        queryHistory = mergeUniqueStrings(remoteHistory, queryHistory).slice(0, MAX_HISTORY);
        this.saveFavorites(favorites);
        this.saveQueryHistory(queryHistory);
      } catch (_err) {
        // keep local cache fallback
      }
    }

    this.setData({
      favorites,
      queryHistory,
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
        rankingsReady: true,
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
        rankingsReady: true,
        rankingsError: hint,
      });
    }
  },

  onToggleRankings() {
    const next = !this.data.showRankings;
    this.setData({ showRankings: next });
    if (next && !this.data.rankingsReady && !this.data.rankingsLoading) {
      this.loadTodayRankings();
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
    const nearbyEnabled = !!this.data.preferNearby;
    const locationContext = nearbyEnabled ? (this.data.locationContext || null) : null;
    const baseQuery = forceRefine ? buildRefinedQuery(cleanQuery, dislikedNames) : cleanQuery;
    const nearbyHint = nearbyEnabled ? buildNearbyHintText(locationContext) : "";
    const requestQuery = nearbyHint ? `${baseQuery}。${nearbyHint}` : baseQuery;

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
        preferNearby: nearbyEnabled && !!locationContext,
        location: locationContext
          ? {
            latitude: locationContext.latitude,
            longitude: locationContext.longitude,
            campus: locationContext.campus,
            areaHint: locationContext.areaHint,
            accuracy: locationContext.accuracy,
          }
          : undefined,
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
      let summarySuffix = "";
      if (forceRefine) summarySuffix += "（已按你的反馈换口味）";
      if (nearbyEnabled && locationContext) summarySuffix += "（已启用附近优先）";

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

  async onTogglePreferNearby() {
    if (this.data.loading || this.data.locationLoading) return;
    if (this.data.preferNearby) {
      this.setData({ preferNearby: false, locationError: "" });
      wx.showToast({ title: "已关闭附近优先", icon: "none" });
      return;
    }

    const context = await this.ensureLocationContext();
    if (!context) return;

    this.setData({ preferNearby: true, locationError: "" });
    wx.showToast({
      title: `附近优先：${this.formatLocationLabel(context)}`,
      icon: "none",
    });
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
    const rank = Number(e.currentTarget.dataset.rank);
    const score = Number(e.currentTarget.dataset.score);
    trackEvent({
      eventType: "recommendation_conversion",
      source: "miniprogram_inquiry_recommend_card",
      queryText: this.data.query || "",
      shopId: storeName,
      shopName: storeName,
      meta: {
        rank: Number.isFinite(rank) ? rank : null,
        score: Number.isFinite(score) ? score : null,
        onlyOpenNow: !!this.data.onlyOpenNow,
        preferNearby: !!this.data.preferNearby,
      },
    });
    wx.navigateTo({
      url: `/pages/store-detail/index?name=${encodeURIComponent(storeName)}`,
    });
  },

  async onToggleFavorite(e) {
    const name = (e.currentTarget.dataset.name || "").trim();
    if (!name) return;
    const current = this.data.favorites || [];
    const exists = current.includes(name);
    const next = exists ? current.filter((item) => item !== name) : [name].concat(current).slice(0, MAX_FAVORITES);
    this.saveFavorites(next);
    if (this.identity && this.identity.userId) {
      try {
        if (exists) {
          await removeFavorite({
            userId: this.identity.userId,
            shopId: name,
          });
        } else {
          await addFavorite({
            userId: this.identity.userId,
            anonymousId: this.identity.anonymousId,
            shopId: name,
            shopName: name,
            source: "miniprogram_favorite",
          });
        }
      } catch (_err) {
        this.saveFavorites(current);
        wx.showToast({ title: "收藏同步失败，请稍后再试", icon: "none" });
        return;
      }
    }
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

    let currentVisible = pickCardNames(this.data.visibleCards);
    let overlap = currentVisible.filter((name) => previousVisible.includes(name));
    if (overlap.length === 0 || currentVisible.length === 0) return;

    // Retry once with an expanded exclusion set so "鎹㈠彛鍛? is more visibly different.
    const retryDisliked = mergeDislikedNames(nextDisliked, currentVisible);
    if (retryDisliked.length <= nextDisliked.length) {
      wx.showToast({ title: "宸插敖閲忔崲鍙ｅ懗锛屽彲鍐嶇偣涓€娆＄户缁崲", icon: "none" });
      return;
    }

    this.setData({ dislikedNames: retryDisliked });
    const retried = await this.runRecommendation(query, {
      forceRefine: true,
      dislikedNames: retryDisliked,
    });
    if (!retried) return;

    currentVisible = pickCardNames(this.data.visibleCards);
    overlap = currentVisible.filter((name) => previousVisible.includes(name));
    if (overlap.length > 0 && currentVisible.length > 0) {
      wx.showToast({ title: "候选池有限，已尽量换口味", icon: "none" });
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
    wx.showToast({ title: "宸叉竻闄ゆ帓闄ら」", icon: "none" });
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
        title: err && err.message ? err.message : "鎻愪氦澶辫触锛岃绋嶅悗閲嶈瘯",
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
        title: err && err.message ? err.message : "鎻愪氦澶辫触锛岃绋嶅悗閲嶈瘯",
        icon: "none",
      });
    }
  },
});




