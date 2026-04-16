const { wechatLogin, fetchProfileData, syncProfileLocal } = require("../../utils/api");
const { getCurrentIdentity, saveAuthenticatedIdentity } = require("../../utils/identity");

const MAX_HISTORY = 8;
const MAX_FAVORITES = 50;

Page({
  data: {
    identityLabel: "匿名使用",
    anonymousIdShort: "",
    isAuthenticated: false,
    loginLoading: false,
    favoritesCount: 0,
    queryHistoryCount: 0,
    locationEnabled: false,
  },

  onShow() {
    this.refreshProfile();
  },

  getStorageKeys(identity = this.identity) {
    const anon = identity && identity.anonymousId ? identity.anonymousId : "anonymous";
    return {
      favoritesKey: `chedian.minip.favorites.${anon}`,
      historyKey: `chedian.minip.history.${anon}`,
    };
  },

  readLocalData(identity = this.identity) {
    const keys = this.getStorageKeys(identity);
    const favorites = wx.getStorageSync(keys.favoritesKey);
    const queryHistory = wx.getStorageSync(keys.historyKey);
    return {
      favorites: Array.isArray(favorites) ? favorites.slice(0, MAX_FAVORITES) : [],
      queryHistory: Array.isArray(queryHistory) ? queryHistory.slice(0, MAX_HISTORY) : [],
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

  async refreshProfile() {
    const identity = getCurrentIdentity();
    this.identity = identity;
    const anon = identity.anonymousId || "anonymous";

    let local = this.readLocalData(identity);
    if (identity.kind === "authenticated" && identity.userId) {
      try {
        const remote = await fetchProfileData(identity.userId);
        const remoteFavorites = Array.isArray(remote && remote.favorites) ? remote.favorites : [];
        const remoteHistory = Array.isArray(remote && remote.queryHistory) ? remote.queryHistory : [];
        local = this.persistLocalData(remoteFavorites, remoteHistory, identity);
      } catch (_err) {
        // use local fallback when profile API is unavailable
      }
    }

    this.setData({
      identityLabel: identity.kind === "authenticated" ? "微信已登录" : "匿名使用",
      isAuthenticated: identity.kind === "authenticated",
      anonymousIdShort: anon ? anon.slice(-8) : "",
      favoritesCount: local.favorites.length,
      queryHistoryCount: local.queryHistory.length,
    });

    wx.getSetting({
      success: (res) => {
        const auth = res.authSetting || {};
        this.setData({
          locationEnabled: !!auth["scope.userLocation"],
        });
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
      if (!resp || !resp.ok || !resp.userId) {
        throw new Error((resp && resp.error) || "微信登录失败，请稍后再试");
      }

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
        // login can still proceed even when migration API is temporarily unavailable
      }

      this.identity = saveAuthenticatedIdentity(
        resp.userId,
        resp.anonymousId || (beforeIdentity && beforeIdentity.anonymousId)
      );

      if (syncResp && syncResp.ok) {
        this.persistLocalData(syncResp.favorites || [], syncResp.queryHistory || [], this.identity);
      } else {
        this.persistLocalData(localBefore.favorites, localBefore.queryHistory, this.identity);
      }

      await this.refreshProfile();
      wx.showToast({ title: "微信登录成功", icon: "success" });
    } catch (err) {
      wx.showToast({
        title: err && err.message ? err.message : "微信登录失败",
        icon: "none",
      });
    } finally {
      this.setData({ loginLoading: false });
    }
  },

  onOpenLocationSetting() {
    wx.openSetting({
      success: () => {
        this.refreshProfile();
      },
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
});
