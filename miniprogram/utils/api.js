const { API_BASE_URL } = require("./config");

function request({ url, method = "GET", data = undefined, timeout = 90000 }) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${API_BASE_URL}${url}`,
      method,
      data,
      timeout,
      header: {
        "content-type": "application/json; charset=utf-8",
        Accept: "application/json; charset=utf-8",
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data || {});
          return;
        }
        reject(new Error(`HTTP ${res.statusCode}`));
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
  wechatLogin,
  fetchProfileData,
  syncProfileLocal,
  addFavorite,
  removeFavorite,
  API_BASE_URL,
};
