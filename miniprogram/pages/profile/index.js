const {
  wechatLogin,
  fetchProfileData,
  syncProfileLocal,
  fetchProfileSettings,
  saveProfileSettings,
  removeFavorite,
} = require("../../utils/api");
const { getCurrentIdentity, saveAuthenticatedIdentity } = require("../../utils/identity");
const { trackEvent } = require("../../utils/analytics");

const MAX_HISTORY = 8;
const MAX_FAVORITES = 50;
const MAX_TASTE_PREFERENCES = 6;
const MAX_HIDDEN_HISTORY = 120;
const TASTE_OPTIONS = ["想吃辣", "想吃面", "预算低", "一个人吃", "夜宵", "清淡", "重口", "想喝汤"];
const QUICK_CONDITIONS = ["更近", "便宜点", "营业中", "换一批", "适合一个人"];

function buildTasteOptionViews(selectedList) {
  const selected = Array.isArray(selectedList) ? selectedList : [];
  return TASTE_OPTIONS.map((label) => ({
    label,
    selected: selected.includes(label),
  }));
}

function parseAvatarText(name, fallback) {
  const value = String(name || "").trim();
  if (!value) return fallback;
  return value.slice(0, 1);
}

function hasWechatProfile(meta) {
  if (!meta || typeof meta !== "object") return false;
  return Boolean(String(meta.nickname || "").trim() || String(meta.avatarUrl || "").trim());
}

function normalizeTasteTags(values) {
  if (!Array.isArray(values)) return [];
  return values
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .slice(0, MAX_TASTE_PREFERENCES);
}

function arraysEqual(a, b) {
  const left = Array.isArray(a) ? a : [];
  const right = Array.isArray(b) ? b : [];
  if (left.length !== right.length) return false;
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] !== right[i]) return false;
  }
  return true;
}

Page({
  data: {
    isAuthenticated: false,
    loginLoading: false,
    favoritesCount: 0,
    queryHistoryCount: 0,
    locationEnabled: false,
    tastePreferences: [],
    quickConditions: QUICK_CONDITIONS,
    strategyItems: [],
    tastePanelVisible: false,
    tasteDraft: [],
    maxTasteCount: MAX_TASTE_PREFERENCES,
    tasteOptionViews: buildTasteOptionViews([]),
    profileAvatarUrl: "",
    profileDisplayName: "点击登录",
    profileSubtitle: "登录后可同步收藏、历史记录与个性化推荐",
    profileActionText: "去登录",
    profileAvatarText: "登",
    favorites: [],
    queryHistory: [],
  },

  onShow() {
    this.refreshProfile();
  },

  getStorageKeys(identity = this.identity) {
    const anon = identity && identity.anonymousId ? identity.anonymousId : "anonymous";
    return {
      favoritesKey: `chedian.minip.favorites.${anon}`,
      historyKey: `chedian.minip.history.${anon}`,
      historyHiddenKey: `chedian.minip.historyHidden.${anon}`,
      tastePrefKey: `chedian.minip.tastePref.${anon}`,
      profileMetaKey: `chedian.minip.profileMeta.${anon}`,
    };
  },

  readProfileMetaRaw(identity = this.identity) {
    const keys = this.getStorageKeys(identity);
    const raw = wx.getStorageSync(keys.profileMetaKey);
    if (!raw || typeof raw !== "object") {
      return {};
    }
    return { ...raw };
  },

  readProfileMeta(identity = this.identity) {
    const raw = this.readProfileMetaRaw(identity);
    return {
      nickname: String(raw.nickname || "").trim(),
      avatarUrl: String(raw.avatarUrl || "").trim(),
    };
  },

  upsertProfileMeta(partial, identity = this.identity) {
    const keys = this.getStorageKeys(identity);
    const prev = this.readProfileMetaRaw(identity);
    const next = {
      ...prev,
      ...partial,
    };
    wx.setStorageSync(keys.profileMetaKey, next);
    return next;
  },

  readLocalData(identity = this.identity) {
    const keys = this.getStorageKeys(identity);
    const favorites = wx.getStorageSync(keys.favoritesKey);
    const queryHistory = wx.getStorageSync(keys.historyKey);
    const hiddenHistory = wx.getStorageSync(keys.historyHiddenKey);
    const tastePreferences = wx.getStorageSync(keys.tastePrefKey);
    return {
      favorites: Array.isArray(favorites) ? favorites.slice(0, MAX_FAVORITES) : [],
      queryHistory: Array.isArray(queryHistory) ? queryHistory.slice(0, MAX_HISTORY) : [],
      hiddenHistory: Array.isArray(hiddenHistory)
        ? hiddenHistory
            .slice(0, MAX_HIDDEN_HISTORY)
            .map((item) => String(item || "").trim())
            .filter(Boolean)
        : [],
      tastePreferences: Array.isArray(tastePreferences)
        ? tastePreferences
            .slice(0, MAX_TASTE_PREFERENCES)
            .map((item) => String(item || "").trim())
            .filter(Boolean)
        : [],
    };
  },

  persistLocalData(favorites, queryHistory, identity = this.identity) {
    const keys = this.getStorageKeys(identity);
    const nextFavorites = Array.isArray(favorites) ? favorites.slice(0, MAX_FAVORITES) : [];
    const nextHistory = Array.isArray(queryHistory) ? queryHistory.slice(0, MAX_HISTORY) : [];
    wx.setStorageSync(keys.favoritesKey, nextFavorites);
    wx.setStorageSync(keys.historyKey, nextHistory);
    return {
      favorites: nextFavorites,
      queryHistory: nextHistory,
    };
  },

  writeFavorites(favorites, identity = this.identity) {
    const keys = this.getStorageKeys(identity);
    const next = Array.isArray(favorites)
      ? favorites
          .slice(0, MAX_FAVORITES)
          .map((item) => String(item || "").trim())
          .filter(Boolean)
      : [];
    wx.setStorageSync(keys.favoritesKey, next);
    return next;
  },

  writeQueryHistory(queryHistory, identity = this.identity) {
    const keys = this.getStorageKeys(identity);
    const next = Array.isArray(queryHistory)
      ? queryHistory
          .slice(0, MAX_HISTORY)
          .map((item) => String(item || "").trim())
          .filter(Boolean)
      : [];
    wx.setStorageSync(keys.historyKey, next);
    return next;
  },

  writeHiddenHistory(hiddenHistory, identity = this.identity) {
    const keys = this.getStorageKeys(identity);
    const next = Array.isArray(hiddenHistory)
      ? hiddenHistory
          .slice(0, MAX_HIDDEN_HISTORY)
          .map((item) => String(item || "").trim())
          .filter(Boolean)
      : [];
    wx.setStorageSync(keys.historyHiddenKey, next);
    return next;
  },

  saveTastePreferences(tags, identity = this.identity) {
    const keys = this.getStorageKeys(identity);
    const normalized = Array.isArray(tags)
      ? tags.map((item) => String(item || "").trim()).filter(Boolean).slice(0, MAX_TASTE_PREFERENCES)
      : [];
    wx.setStorageSync(keys.tastePrefKey, normalized);
    return normalized;
  },

  buildStrategyItems({ locationEnabled }) {
    return [
      {
        key: "nearby",
        label: "附近优先",
        active: !!locationEnabled,
      },
      {
        key: "open",
        label: "营业中优先",
        active: true,
      },
      {
        key: "dedupe",
        label: "尽量避免重复推荐",
        active: true,
      },
    ];
  },

  composeProfileCardView(meta, isAuthenticated) {
    const synced = hasWechatProfile(meta);
    const profileDisplayName = isAuthenticated ? meta.nickname || "微信用户" : "点击登录";
    const profileSubtitle = isAuthenticated
      ? synced
        ? "已为你保存收藏、历史与推荐偏好"
        : "点击同步微信头像昵称，完善个人资料"
      : "登录后可同步收藏、历史记录与个性化推荐";
    const profileActionText = isAuthenticated ? (synced ? "编辑资料" : "同步资料") : "去登录";
    const profileAvatarUrl = isAuthenticated ? meta.avatarUrl : "";
    const profileAvatarText = parseAvatarText(profileDisplayName, isAuthenticated ? "我" : "登");
    return {
      profileDisplayName,
      profileSubtitle,
      profileActionText,
      profileAvatarUrl,
      profileAvatarText,
    };
  },

  async refreshProfile() {
    const identity = getCurrentIdentity();
    this.identity = identity;

    let local = this.readLocalData(identity);
    const hiddenSet = new Set(local.hiddenHistory || []);
    if (identity.kind === "authenticated" && identity.userId) {
      try {
        const remote = await fetchProfileData(identity.userId);
        const remoteFavorites = Array.isArray(remote && remote.favorites) ? remote.favorites : [];
        const remoteHistoryRaw = Array.isArray(remote && remote.queryHistory) ? remote.queryHistory : [];
        const remoteHistory = remoteHistoryRaw.filter((item) => !hiddenSet.has(String(item || "").trim()));
        local = {
          ...local,
          ...this.persistLocalData(remoteFavorites, remoteHistory, identity),
        };
      } catch (_err) {
        // Use local fallback when profile API is unavailable.
      }

      try {
        const settingsResp = await fetchProfileSettings(identity.userId);
        const remoteTaste = normalizeTasteTags(settingsResp && settingsResp.profile && settingsResp.profile.tasteTags);
        local = {
          ...local,
          tastePreferences: remoteTaste,
        };
        this.saveTastePreferences(remoteTaste, identity);
      } catch (_err) {
        // Keep local taste preferences when profile settings API is unavailable.
      }
    }

    const isAuthenticated = identity.kind === "authenticated";
    const profileMeta = this.readProfileMeta(identity);
    const cardView = this.composeProfileCardView(profileMeta, isAuthenticated);

    wx.getSetting({
      success: (res) => {
        const auth = res.authSetting || {};
        const locationEnabled = !!auth["scope.userLocation"];
        this.setData({
          isAuthenticated,
          favoritesCount: local.favorites.length,
          queryHistoryCount: local.queryHistory.length,
          favorites: local.favorites,
          queryHistory: local.queryHistory,
          tastePreferences: local.tastePreferences,
          tasteOptionViews: buildTasteOptionViews(local.tastePreferences),
          locationEnabled,
          strategyItems: this.buildStrategyItems({ locationEnabled }),
          ...cardView,
        });
      },
      fail: () => {
        const locationEnabled = false;
        this.setData({
          isAuthenticated,
          favoritesCount: local.favorites.length,
          queryHistoryCount: local.queryHistory.length,
          favorites: local.favorites,
          queryHistory: local.queryHistory,
          tastePreferences: local.tastePreferences,
          tasteOptionViews: buildTasteOptionViews(local.tastePreferences),
          locationEnabled,
          strategyItems: this.buildStrategyItems({ locationEnabled }),
          ...cardView,
        });
      },
    });
  },

  onSyncWechatProfile(options = {}) {
    if (!this.data.isAuthenticated) {
      wx.showToast({ title: "请先微信登录", icon: "none" });
      return;
    }
    if (typeof wx.getUserProfile !== "function") {
      wx.showToast({ title: "当前基础库不支持资料授权", icon: "none" });
      if (options.navigateAfter) {
        wx.navigateTo({ url: "/pages/profile-detail/index" });
      }
      return;
    }

    wx.getUserProfile({
      desc: "用于展示你的头像和昵称",
      lang: "zh_CN",
      success: async (res) => {
        const userInfo = (res && res.userInfo) || {};
        const nickname = String(userInfo.nickName || "").trim();
        const avatarUrl = String(userInfo.avatarUrl || "").trim();
        if (!nickname && !avatarUrl) {
          wx.showToast({ title: "未获取到微信资料", icon: "none" });
          return;
        }
        this.upsertProfileMeta(
          {
            nickname,
            avatarUrl,
            wechatSyncedAt: new Date().toISOString(),
          },
          this.identity
        );
        await this.refreshProfile();
        wx.showToast({ title: "微信资料已同步", icon: "success" });
        if (options.navigateAfter) {
          setTimeout(() => {
            wx.navigateTo({ url: "/pages/profile-detail/index" });
          }, 180);
        }
      },
      fail: (err) => {
        const msg = String((err && err.errMsg) || "");
        if (!msg.includes("cancel")) {
          wx.showToast({ title: "微信资料授权失败", icon: "none" });
        } else if (options.navigateAfter) {
          wx.navigateTo({ url: "/pages/profile-detail/index" });
        }
      },
    });
  },

  maybePromptWechatProfileSync() {
    if (!this.data.isAuthenticated) return;
    if (typeof wx.getUserProfile !== "function") return;
    const meta = this.readProfileMeta(this.identity);
    if (hasWechatProfile(meta)) return;

    wx.showModal({
      title: "同步微信资料",
      content: "授权后可自动显示微信头像和昵称",
      confirmText: "去授权",
      cancelText: "稍后",
      success: (res) => {
        if (res.confirm) {
          this.onSyncWechatProfile();
        }
      },
    });
  },

  async onWechatLogin() {
    if (this.data.loginLoading) return;
    if (this.identity && this.identity.kind === "authenticated") {
      wx.showToast({ title: "当前已微信登录", icon: "none" });
      return;
    }

    this.setData({ loginLoading: true });
    try {
      const beforeIdentity = this.identity || getCurrentIdentity();
      const localBefore = this.readLocalData(beforeIdentity);

      const loginResult = await new Promise((resolve, reject) => {
        wx.login({
          success: (res) => {
            if (res && res.code) {
              resolve(res);
              return;
            }
            reject(new Error("wx.login 未返回 code"));
          },
          fail: (err) => reject(new Error((err && err.errMsg) || "wx.login 失败")),
        });
      });

      const resp = await wechatLogin({
        code: loginResult.code,
        anonymousId: beforeIdentity ? beforeIdentity.anonymousId : undefined,
      });
      if (!resp || !resp.ok || !resp.userId || !resp.accessToken) {
        throw new Error((resp && resp.error) || "微信登录失败，请稍后再试");
      }

      this.identity = saveAuthenticatedIdentity(
        resp.userId,
        resp.anonymousId || (beforeIdentity && beforeIdentity.anonymousId),
        {
          accessToken: resp.accessToken,
          tokenType: resp.tokenType,
          expiresIn: resp.expiresIn,
        }
      );

      let syncResp = null;
      try {
        syncResp = await syncProfileLocal({
          userId: resp.userId,
          anonymousId: beforeIdentity ? beforeIdentity.anonymousId : undefined,
          favorites: localBefore.favorites,
          queryHistory: localBefore.queryHistory,
          source: "miniprogram_profile",
        });
      } catch (_syncErr) {
        // Login can still proceed even when migration API is unavailable.
      }

      if (syncResp && syncResp.ok) {
        this.persistLocalData(syncResp.favorites || [], syncResp.queryHistory || [], this.identity);
      } else {
        this.persistLocalData(localBefore.favorites, localBefore.queryHistory, this.identity);
      }
      this.saveTastePreferences(localBefore.tastePreferences || [], this.identity);

      await this.refreshProfile();
      wx.showToast({ title: "微信登录成功", icon: "success" });
      setTimeout(() => {
        this.maybePromptWechatProfileSync();
      }, 180);
    } catch (err) {
      wx.showToast({
        title: err && err.message ? err.message : "微信登录失败",
        icon: "none",
      });
    } finally {
      this.setData({ loginLoading: false });
    }
  },

  onTapProfileCard() {
    const meta = this.readProfileMeta(this.identity);
    trackEvent({
      eventType: "profile_card_click",
      source: "miniprogram_profile_home",
      meta: {
        isAuthenticated: !!this.data.isAuthenticated,
        hasWechatProfile: hasWechatProfile(meta),
      },
    });

    if (this.data.loginLoading) return;
    if (!this.data.isAuthenticated) {
      this.onWechatLogin();
      return;
    }
    if (!hasWechatProfile(meta)) {
      this.onSyncWechatProfile({ navigateAfter: true });
      return;
    }
    wx.navigateTo({
      url: "/pages/profile-detail/index",
    });
  },

  onOpenLocationSetting() {
    wx.openSetting({
      success: () => {
        this.refreshProfile();
      },
    });
  },

  onOpenTasteSetting() {
    const current = Array.isArray(this.data.tastePreferences) ? this.data.tastePreferences : [];
    this.setData({
      tastePanelVisible: true,
      tasteDraft: [...current],
      tasteOptionViews: buildTasteOptionViews(current),
    });
  },

  onCloseTasteSetting() {
    const current = Array.isArray(this.data.tastePreferences) ? this.data.tastePreferences : [];
    this.setData({
      tastePanelVisible: false,
      tasteDraft: [...current],
      tasteOptionViews: buildTasteOptionViews(current),
    });
  },

  onToggleTasteTag(e) {
    const label = String((e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.tag) || "").trim();
    if (!label) return;

    let next = Array.isArray(this.data.tasteDraft) ? [...this.data.tasteDraft] : [];
    if (next.includes(label)) {
      next = next.filter((item) => item !== label);
    } else {
      if (next.length >= MAX_TASTE_PREFERENCES) {
        wx.showToast({ title: `最多选择 ${MAX_TASTE_PREFERENCES} 项`, icon: "none" });
        return;
      }
      next.push(label);
    }

    this.setData({
      tasteDraft: next,
      tasteOptionViews: buildTasteOptionViews(next),
    });
  },

  onClearTasteDraft() {
    this.setData({
      tasteDraft: [],
      tasteOptionViews: buildTasteOptionViews([]),
    });
  },

  async onConfirmTasteSetting() {
    const before = normalizeTasteTags(this.data.tastePreferences || []);
    const saved = this.saveTastePreferences(this.data.tasteDraft || [], this.identity);
    let synced = true;
    if (this.identity && this.identity.kind === "authenticated" && this.identity.userId) {
      try {
        await saveProfileSettings({
          userId: this.identity.userId,
          anonymousId: this.identity.anonymousId || undefined,
          tasteTags: saved,
          source: "miniprogram_profile_taste",
        });
      } catch (_err) {
        synced = false;
      }
    }
    this.setData({
      tastePanelVisible: false,
      tastePreferences: saved,
      tasteDraft: [...saved],
      tasteOptionViews: buildTasteOptionViews(saved),
    });
    if (!arraysEqual(before, saved)) {
      trackEvent({
        eventType: "preference_change",
        source: "miniprogram_profile_quick_taste",
        meta: {
          changedFields: ["tasteTags"],
          beforeCount: before.length,
          afterCount: saved.length,
          syncedCloud: synced,
        },
      });
    }
    wx.showToast({ title: synced ? "口味偏好已更新" : "已保存本地，云端同步失败", icon: "none" });
  },

  onUseQuickCondition(e) {
    const label = String((e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.label) || "").trim();
    if (!label) return;
    wx.setStorageSync("chedian.minip.quickCondition", label);
    wx.showToast({ title: `已记录：${label}`, icon: "none" });
    wx.switchTab({
      url: "/pages/index/index",
    });
  },

  onOpenFavoriteDetail(e) {
    const name = String((e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.name) || "").trim();
    if (!name) return;
    wx.navigateTo({
      url: `/pages/store-detail/index?name=${encodeURIComponent(name)}`,
    });
  },

  async onDeleteFavoriteItem(e) {
    const name = String((e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.name) || "").trim();
    if (!name) return;

    const current = Array.isArray(this.data.favorites) ? this.data.favorites : [];
    const next = current.filter((item) => item !== name);
    if (next.length === current.length) return;

    this.writeFavorites(next, this.identity);
    this.setData({
      favorites: next,
      favoritesCount: next.length,
    });

    if (this.identity && this.identity.kind === "authenticated" && this.identity.userId) {
      try {
        await removeFavorite({
          userId: this.identity.userId,
          shopId: name,
        });
      } catch (_err) {
        this.writeFavorites(current, this.identity);
        this.setData({
          favorites: current,
          favoritesCount: current.length,
        });
        wx.showToast({ title: "删除失败，请稍后再试", icon: "none" });
        return;
      }
    }
    wx.showToast({ title: "已删除收藏", icon: "none" });
  },

  onRerunFavoriteItem(e) {
    const name = String((e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.name) || "").trim();
    if (!name) return;
    wx.removeStorageSync("chedian.minip.pendingQueryPreview");
    wx.setStorageSync("chedian.minip.pendingQuery", name);
    wx.switchTab({
      url: "/pages/index/index",
    });
  },

  onViewHistoryItem(e) {
    const query = String((e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.query) || "").trim();
    if (!query) return;
    wx.removeStorageSync("chedian.minip.pendingQuery");
    wx.setStorageSync("chedian.minip.pendingQueryPreview", query);
    wx.switchTab({
      url: "/pages/index/index",
    });
  },

  onDeleteHistoryItem(e) {
    const query = String((e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.query) || "").trim();
    if (!query) return;

    const current = Array.isArray(this.data.queryHistory) ? this.data.queryHistory : [];
    const next = current.filter((item) => item !== query);
    if (next.length === current.length) return;

    const local = this.readLocalData(this.identity);
    const hiddenBefore = Array.isArray(local.hiddenHistory) ? local.hiddenHistory : [];
    const hiddenNext = [query].concat(hiddenBefore.filter((item) => item !== query)).slice(0, MAX_HIDDEN_HISTORY);
    this.writeHiddenHistory(hiddenNext, this.identity);
    this.writeQueryHistory(next, this.identity);
    this.setData({
      queryHistory: next,
      queryHistoryCount: next.length,
    });
    wx.showToast({ title: "已删除记录", icon: "none" });
  },

  onRerunHistoryItem(e) {
    const query = String((e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.query) || "").trim();
    if (!query) return;
    wx.removeStorageSync("chedian.minip.pendingQueryPreview");
    wx.setStorageSync("chedian.minip.pendingQuery", query);
    wx.switchTab({
      url: "/pages/index/index",
    });
  },

  onGoInquiry() {
    wx.switchTab({
      url: "/pages/index/index",
    });
  },

  onGoAds() {
    wx.switchTab({
      url: "/pages/ads/index",
    });
  },

  stopTap() {},
});
