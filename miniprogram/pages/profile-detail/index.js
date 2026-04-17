const { fetchProfileSettings, saveProfileSettings } = require("../../utils/api");
const { getCurrentIdentity } = require("../../utils/identity");
const { trackEvent } = require("../../utils/analytics");

const MAX_TASTE_PREFERENCES = 6;
const TASTE_OPTIONS = ["想吃辣", "想吃面", "预算低", "一个人吃", "夜宵", "清淡", "重口", "想喝汤"];
const CAMPUS_OPTIONS = ["清水河", "沙河", "两校区都常去", "其他"];
const BUDGET_OPTIONS = ["20元以内", "20-35元", "35-50元", "50元以上", "不设预算"];

function buildTasteOptionViews(selectedList) {
  const selected = Array.isArray(selectedList) ? selectedList : [];
  return TASTE_OPTIONS.map((label) => ({
    label,
    selected: selected.includes(label),
  }));
}

function parseAvatarText(name) {
  const text = String(name || "").trim();
  return text ? text.slice(0, 1) : "我";
}

function parseDislikes(value) {
  return String(value || "")
    .split(/[,，、/\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 10);
}

function toDislikesInput(dislikes) {
  return Array.isArray(dislikes) ? dislikes.filter(Boolean).join("、") : "";
}

function normalizeTasteTags(values) {
  if (!Array.isArray(values)) return [];
  return values
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .slice(0, MAX_TASTE_PREFERENCES);
}

function pickCampus(value) {
  const text = String(value || "").trim();
  if (!text) return CAMPUS_OPTIONS[0];
  return CAMPUS_OPTIONS.includes(text) ? text : CAMPUS_OPTIONS[0];
}

function pickBudget(value) {
  const text = String(value || "").trim();
  if (!text) return BUDGET_OPTIONS[BUDGET_OPTIONS.length - 1];
  return BUDGET_OPTIONS.includes(text) ? text : BUDGET_OPTIONS[BUDGET_OPTIONS.length - 1];
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
    avatarUrl: "",
    nickname: "",
    campusOptions: CAMPUS_OPTIONS,
    campusIndex: 0,
    tasteSelections: [],
    tasteOptionViews: buildTasteOptionViews([]),
    maxTasteCount: MAX_TASTE_PREFERENCES,
    dislikesInput: "",
    budgetOptions: BUDGET_OPTIONS,
    budgetIndex: BUDGET_OPTIONS.length - 1,
    saving: false,
    avatarText: "我",
    syncingWechat: false,
    syncedWechatAtText: "",
  },

  onShow() {
    this.loadProfile();
  },

  getStorageKeys(identity = this.identity) {
    const anon = identity && identity.anonymousId ? identity.anonymousId : "anonymous";
    return {
      profileMetaKey: `chedian.minip.profileMeta.${anon}`,
      tastePrefKey: `chedian.minip.tastePref.${anon}`,
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

  readProfileMeta(identity = this.identity) {
    const raw = this.readProfileMetaRaw(identity);
    return {
      nickname: String(raw.nickname || "").trim(),
      avatarUrl: String(raw.avatarUrl || "").trim(),
      campus: pickCampus(raw.campus),
      dislikes: Array.isArray(raw.dislikes) ? raw.dislikes.map((x) => String(x || "").trim()).filter(Boolean) : [],
      budgetPreference: pickBudget(raw.budgetPreference),
      wechatSyncedAt: String(raw.wechatSyncedAt || "").trim(),
    };
  },

  readTastePreferences(identity = this.identity) {
    const keys = this.getStorageKeys(identity);
    const raw = wx.getStorageSync(keys.tastePrefKey);
    return normalizeTasteTags(raw);
  },

  writeTastePreferences(tasteSelections, identity = this.identity) {
    const keys = this.getStorageKeys(identity);
    const normalized = normalizeTasteTags(tasteSelections);
    wx.setStorageSync(keys.tastePrefKey, normalized);
    return normalized;
  },

  formatSyncedTime(isoText) {
    const value = String(isoText || "").trim();
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    const hh = String(date.getHours()).padStart(2, "0");
    const mm = String(date.getMinutes()).padStart(2, "0");
    return `${y}-${m}-${d} ${hh}:${mm}`;
  },

  async fetchRemoteSettings(userId) {
    try {
      const res = await fetchProfileSettings(userId);
      const profile = (res && res.profile) || {};
      return {
        campus: pickCampus(profile.campus),
        tasteTags: normalizeTasteTags(profile.tasteTags),
        dislikes: Array.isArray(profile.dislikes)
          ? profile.dislikes.map((item) => String(item || "").trim()).filter(Boolean).slice(0, 10)
          : [],
        budgetPreference: pickBudget(profile.budgetPreference),
      };
    } catch (_err) {
      return null;
    }
  },

  async loadProfile() {
    const identity = getCurrentIdentity();
    this.identity = identity;

    const localMeta = this.readProfileMeta(identity);
    let campus = localMeta.campus;
    let tasteTags = this.readTastePreferences(identity);
    let dislikes = localMeta.dislikes;
    let budgetPreference = localMeta.budgetPreference;

    if (identity.kind === "authenticated" && identity.userId) {
      const remote = await this.fetchRemoteSettings(identity.userId);
      if (remote) {
        campus = remote.campus;
        tasteTags = remote.tasteTags;
        dislikes = remote.dislikes;
        budgetPreference = remote.budgetPreference;
        this.upsertProfileMeta(
          {
            campus,
            dislikes,
            budgetPreference,
          },
          identity
        );
        this.writeTastePreferences(tasteTags, identity);
      }
    }

    const campusIndex = Math.max(0, CAMPUS_OPTIONS.indexOf(campus));
    const budgetIndex = Math.max(0, BUDGET_OPTIONS.indexOf(budgetPreference));

    const displayName = localMeta.nickname || (identity.kind === "authenticated" ? "微信用户" : "");
    this.profileSnapshot = {
      campus,
      tasteTags,
      dislikes,
      budgetPreference,
    };
    this.setData({
      isAuthenticated: identity.kind === "authenticated",
      avatarUrl: localMeta.avatarUrl,
      nickname: displayName,
      campusIndex,
      tasteSelections: tasteTags,
      tasteOptionViews: buildTasteOptionViews(tasteTags),
      dislikesInput: toDislikesInput(dislikes),
      budgetIndex,
      avatarText: parseAvatarText(displayName),
      syncedWechatAtText: this.formatSyncedTime(localMeta.wechatSyncedAt),
    });
  },

  onSyncWechatProfile() {
    if (!this.data.isAuthenticated) {
      wx.showToast({ title: "请先登录后再同步", icon: "none" });
      return;
    }
    if (this.data.syncingWechat) return;
    if (typeof wx.getUserProfile !== "function") {
      wx.showToast({ title: "当前基础库不支持资料授权", icon: "none" });
      return;
    }

    this.setData({ syncingWechat: true });
    wx.getUserProfile({
      desc: "用于展示你的头像和昵称",
      lang: "zh_CN",
      success: (res) => {
        const userInfo = (res && res.userInfo) || {};
        const nickname = String(userInfo.nickName || "").trim();
        const avatarUrl = String(userInfo.avatarUrl || "").trim();
        if (!nickname && !avatarUrl) {
          wx.showToast({ title: "未获取到微信资料", icon: "none" });
          return;
        }
        const syncedAt = new Date().toISOString();
        this.upsertProfileMeta(
          {
            nickname,
            avatarUrl,
            wechatSyncedAt: syncedAt,
          },
          this.identity
        );
        const displayName = nickname || "微信用户";
        this.setData({
          nickname: displayName,
          avatarUrl,
          avatarText: parseAvatarText(displayName),
          syncedWechatAtText: this.formatSyncedTime(syncedAt),
        });
        wx.showToast({ title: "微信资料已同步", icon: "success" });
      },
      fail: (err) => {
        const msg = String((err && err.errMsg) || "");
        if (!msg.includes("cancel")) {
          wx.showToast({ title: "微信资料授权失败", icon: "none" });
        }
      },
      complete: () => {
        this.setData({ syncingWechat: false });
      },
    });
  },

  onChangeCampus(e) {
    const next = Number(e.detail && e.detail.value);
    if (!Number.isFinite(next)) return;
    this.setData({ campusIndex: next });
  },

  onToggleTaste(e) {
    const tag = String((e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.tag) || "").trim();
    if (!tag) return;

    let next = Array.isArray(this.data.tasteSelections) ? [...this.data.tasteSelections] : [];
    if (next.includes(tag)) {
      next = next.filter((item) => item !== tag);
    } else {
      if (next.length >= MAX_TASTE_PREFERENCES) {
        wx.showToast({ title: `最多选择 ${MAX_TASTE_PREFERENCES} 项`, icon: "none" });
        return;
      }
      next.push(tag);
    }
    this.setData({
      tasteSelections: next,
      tasteOptionViews: buildTasteOptionViews(next),
    });
  },

  onDislikesInput(e) {
    const value = String((e.detail && e.detail.value) || "");
    this.setData({ dislikesInput: value });
  },

  onChangeBudget(e) {
    const next = Number(e.detail && e.detail.value);
    if (!Number.isFinite(next)) return;
    this.setData({ budgetIndex: next });
  },

  async onSaveProfile() {
    if (this.data.saving) return;
    this.setData({ saving: true });

    try {
      const campus = CAMPUS_OPTIONS[this.data.campusIndex] || CAMPUS_OPTIONS[0];
      const budgetPreference = BUDGET_OPTIONS[this.data.budgetIndex] || BUDGET_OPTIONS[BUDGET_OPTIONS.length - 1];
      const dislikes = parseDislikes(this.data.dislikesInput);
      const tasteSelections = normalizeTasteTags(this.data.tasteSelections);
      const previous = this.profileSnapshot || {
        campus: "",
        tasteTags: [],
        dislikes: [],
        budgetPreference: "",
      };
      const changedFields = [];
      if (previous.campus !== campus) changedFields.push("campus");
      if (!arraysEqual(previous.tasteTags, tasteSelections)) changedFields.push("tasteTags");
      if (!arraysEqual(previous.dislikes, dislikes)) changedFields.push("dislikes");
      if (previous.budgetPreference !== budgetPreference) changedFields.push("budgetPreference");

      this.upsertProfileMeta(
        {
          campus,
          dislikes,
          budgetPreference,
        },
        this.identity
      );
      this.writeTastePreferences(tasteSelections, this.identity);

      let savedMessage = "资料已保存在本机";
      let syncedCloud = null;
      if (this.identity && this.identity.kind === "authenticated" && this.identity.userId) {
        try {
          await saveProfileSettings({
            userId: this.identity.userId,
            anonymousId: this.identity.anonymousId || undefined,
            campus,
            tasteTags: tasteSelections,
            dislikes,
            budgetPreference,
            source: "miniprogram_profile_detail",
          });
          savedMessage = "资料已同步到云端";
          syncedCloud = true;
        } catch (_err) {
          savedMessage = "已保存本地，云端同步失败";
          syncedCloud = false;
        }
      }

      this.profileSnapshot = {
        campus,
        tasteTags: tasteSelections,
        dislikes,
        budgetPreference,
      };

      trackEvent({
        eventType: "profile_save",
        source: "miniprogram_profile_detail",
        meta: {
          changedCount: changedFields.length,
          changedFields,
          syncedCloud,
        },
      });

      if (changedFields.length > 0) {
        trackEvent({
          eventType: "preference_change",
          source: "miniprogram_profile_detail",
          meta: {
            changedFields,
            campus,
            budgetPreference,
            tasteCount: tasteSelections.length,
            dislikesCount: dislikes.length,
            syncedCloud,
          },
        });
      }

      wx.showToast({ title: savedMessage, icon: "none" });
      setTimeout(() => {
        wx.navigateBack({ delta: 1 });
      }, 240);
    } finally {
      this.setData({ saving: false });
    }
  },
});
