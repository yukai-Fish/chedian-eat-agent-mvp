const { API_BASE_URL } = require("./config");
const { clearAuthenticatedIdentity, getAuthToken } = require("./identity");

function normalizeErrorMessage(statusCode, body) {
  const prefix = `HTTP ${statusCode}`;
  if (body && typeof body === "object") {
    const detail = body.detail;
    if (typeof detail === "string" && detail.trim()) {
      return `${prefix} ${detail.trim()}`;
    }
    if (detail && typeof detail === "object") {
      try {
        const text = JSON.stringify(detail);
        if (text && text !== "{}") return `${prefix} ${text}`;
      } catch (_err) {
        // ignore
      }
    }
    const error = body.error;
    if (typeof error === "string" && error.trim()) {
      return `${prefix} ${error.trim()}`;
    }
  }
  return prefix;
}


function request({ url, method = "GET", data = undefined, timeout = 90000 }) {
  return new Promise((resolve, reject) => {
    const token = getAuthToken();
    const header = {
      "content-type": "application/json; charset=utf-8",
      Accept: "application/json; charset=utf-8",
    };
    if (token) {
      header.Authorization = `Bearer ${token}`;
    }

    wx.request({
      url: `${API_BASE_URL}${url}`,
      method,
      data,
      timeout,
      header,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data || {});
          return;
        }
        if (res.statusCode === 401 && token) {
          clearAuthenticatedIdentity();
        }
        reject(new Error(normalizeErrorMessage(res.statusCode, res.data)));
      },
      fail(err) {
        reject(new Error(err.errMsg || "请求失败"));
      },
    });
  });
}

function fetchRecommendations(payload) {
  return request({
    url: "/api/recommend",
    method: "POST",
    data: payload,
  });
}

function submitFeedback(payload) {
  return request({
    url: "/api/feedback",
    method: "POST",
    data: payload,
  });
}

function fetchStoreDetail(name) {
  const keyword = String(name || "").trim();
  if (!keyword) {
    return Promise.resolve({ found: false, message: "name is required." });
  }
  const encoded = encodeURIComponent(keyword);
  return request({
    url: `/api/stores/detail?name=${encoded}`,
    method: "GET",
  }).catch((err) => {
    const msg = err && err.message ? String(err.message) : "";
    if (!msg.includes("HTTP 404")) throw err;
    // Backward-compatible fallback for environments that only expose /api/v1/*
    return request({
      url: `/api/v1/stores/detail?name=${encoded}`,
      method: "GET",
    });
  });
}

function fetchTodayRankings() {
  return request({
    url: "/api/v1/rankings/today",
    method: "GET",
  });
}

function logRankingClick(payload) {
  return request({
    url: "/api/v1/events/ranking-click",
    method: "POST",
    data: payload,
  });
}

function fetchAdSlots(limit = 10) {
  const topN = Number(limit) || 10;
  return request({
    url: `/api/v1/ads/slots?limit=${encodeURIComponent(topN)}`,
    method: "GET",
  }).catch((err) => {
    const msg = err && err.message ? String(err.message) : "";
    if (!msg.includes("HTTP 404")) throw err;
    return request({
      url: `/api/ads/slots?limit=${encodeURIComponent(topN)}`,
      method: "GET",
    });
  });
}

function logAdClick(payload) {
  return request({
    url: "/api/v1/events/ad-click",
    method: "POST",
    data: payload,
  }).catch((err) => {
    const msg = err && err.message ? String(err.message) : "";
    if (!msg.includes("HTTP 404")) throw err;
    return request({
      url: "/api/events/ad-click",
      method: "POST",
      data: payload,
    });
  });
}

function trackUsageEvent(payload) {
  return request({
    url: "/api/events/track",
    method: "POST",
    data: payload,
  }).catch((err) => {
    const msg = err && err.message ? String(err.message) : "";
    if (!msg.includes("HTTP 404")) throw err;
    return request({
      url: "/api/v1/events/track",
      method: "POST",
      data: payload,
    });
  });
}

function wechatLogin(payload) {
  return request({
    url: "/api/auth/wechat-login",
    method: "POST",
    data: payload,
  });
}

function fetchProfileData(userId) {
  const uid = encodeURIComponent(String(userId || "").trim());
  return request({
    url: `/api/profile/data?user_id=${uid}`,
    method: "GET",
  });
}

function syncProfileLocal(payload) {
  return request({
    url: "/api/profile/sync-local",
    method: "POST",
    data: payload,
  });
}

function fetchProfileSettings(userId) {
  const uid = encodeURIComponent(String(userId || "").trim());
  return request({
    url: `/api/profile/settings?user_id=${uid}`,
    method: "GET",
  }).catch((err) => {
    const msg = err && err.message ? String(err.message) : "";
    if (!msg.includes("HTTP 404")) throw err;
    return request({
      url: `/api/v1/profile/settings?user_id=${uid}`,
      method: "GET",
    });
  });
}

function saveProfileSettings(payload) {
  return request({
    url: "/api/profile/settings",
    method: "POST",
    data: payload,
  }).catch((err) => {
    const msg = err && err.message ? String(err.message) : "";
    if (!msg.includes("HTTP 404")) throw err;
    return request({
      url: "/api/v1/profile/settings",
      method: "POST",
      data: payload,
    });
  });
}

function addFavorite(payload) {
  return request({
    url: "/api/v1/favorites",
    method: "POST",
    data: payload,
  });
}

function removeFavorite(payload) {
  return request({
    url: "/api/v1/favorites",
    method: "DELETE",
    data: payload,
  });
}

module.exports = {
  fetchRecommendations,
  submitFeedback,
  fetchStoreDetail,
  fetchTodayRankings,
  logRankingClick,
  fetchAdSlots,
  logAdClick,
  trackUsageEvent,
  wechatLogin,
  fetchProfileData,
  syncProfileLocal,
  fetchProfileSettings,
  saveProfileSettings,
  addFavorite,
  removeFavorite,
  API_BASE_URL,
};
