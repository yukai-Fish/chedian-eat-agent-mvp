const { fetchStoreDetail } = require("../../utils/api");

function toMinutes(token) {
  const text = String(token || "").trim().replace(/：/g, ":");
  const m = text.match(/^(\d{1,2})\s*:\s*(\d{1,2})$/);
  if (!m) return null;
  const hh = Number(m[1]);
  const mm = Number(m[2]);
  if (!Number.isFinite(hh) || !Number.isFinite(mm)) return null;
  if (hh < 0 || hh > 24 || mm < 0 || mm > 59) return null;
  if (hh === 24 && mm !== 0) return null;
  return hh * 60 + mm;
}

function parseIntervals(openHoursText) {
  const text = String(openHoursText || "").trim();
  if (!text) return [];

  const normalized = text
    .replace(/：/g, ":")
    .replace(/，/g, ",")
    .replace(/；/g, ";")
    .replace(/[~—–]/g, "-")
    .replace(/[至到]/g, "-");

  if (/24小时|全天|24h/i.test(normalized)) {
    return [[0, 24 * 60]];
  }

  const intervals = [];
  const pairRegex = /(\d{1,2}\s*:\s*\d{1,2})\s*-\s*(\d{1,2}\s*:\s*\d{1,2})/g;
  let pairMatch = pairRegex.exec(normalized);
  while (pairMatch) {
    const start = toMinutes(pairMatch[1]);
    const endRaw = toMinutes(pairMatch[2]);
    if (start !== null && endRaw !== null) {
      intervals.push([start, endRaw <= start ? endRaw + 24 * 60 : endRaw]);
    }
    pairMatch = pairRegex.exec(normalized);
  }
  if (intervals.length > 0) return intervals;

  const pointRegex = /(\d{1,2}\s*:\s*\d{1,2})/g;
  const points = [];
  let pointMatch = pointRegex.exec(normalized);
  while (pointMatch) {
    const value = toMinutes(pointMatch[1]);
    if (value !== null) points.push(value);
    pointMatch = pointRegex.exec(normalized);
  }
  for (let i = 0; i + 1 < points.length; i += 2) {
    const start = points[i];
    const endRaw = points[i + 1];
    intervals.push([start, endRaw <= start ? endRaw + 24 * 60 : endRaw]);
  }
  return intervals;
}

function formatHHMM(totalMinutes) {
  const m = ((Number(totalMinutes) || 0) % (24 * 60) + 24 * 60) % (24 * 60);
  const hh = Math.floor(m / 60);
  const mm = m % 60;
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

function computeOpenStatus(openHoursText) {
  const intervals = parseIntervals(openHoursText);
  if (!intervals.length) {
    return {
      status: "unknown",
      label: "营业时间待补充",
      detail: "暂无营业时间信息，建议先看近期评价。",
    };
  }

  const now = new Date();
  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  let openLeft = Number.POSITIVE_INFINITY;
  let closeAt = null;

  intervals.forEach(([start, end]) => {
    [nowMinutes, nowMinutes + 24 * 60].forEach((probe) => {
      if (probe >= start && probe < end) {
        const left = end - probe;
        if (left < openLeft) {
          openLeft = left;
          closeAt = end;
        }
      }
    });
  });

  if (Number.isFinite(openLeft)) {
    if (openLeft <= 60) {
      return {
        status: "closing",
        label: "即将打烊",
        detail: `约 ${Math.max(1, Math.round(openLeft))} 分钟后打烊（${formatHHMM(closeAt)}）`,
      };
    }
    return {
      status: "open",
      label: "营业中",
      detail: `当前可到店（预计 ${formatHHMM(closeAt)} 前营业）`,
    };
  }

  let nextOpenIn = Number.POSITIVE_INFINITY;
  let nextOpenAt = null;
  intervals.forEach(([start]) => {
    [start, start + 24 * 60].forEach((candidate) => {
      const delta = candidate - nowMinutes;
      if (delta > 0 && delta < nextOpenIn) {
        nextOpenIn = delta;
        nextOpenAt = candidate;
      }
    });
  });

  if (!Number.isFinite(nextOpenIn)) {
    return {
      status: "closed",
      label: "休息中",
      detail: "当前不在营业时段。",
    };
  }
  return {
    status: "closed",
    label: "休息中",
    detail: `约 ${Math.round(nextOpenIn)} 分钟后营业（${formatHHMM(nextOpenAt)}）`,
  };
}

function normalizeImageUrls(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => String(item || "").trim())
    .filter((item) => item && (item.startsWith("http://") || item.startsWith("https://") || item.startsWith("/")));
}

function derivePriceBand(avgPrice, minPrice, maxPrice) {
  const base = Number(avgPrice) || 0;
  let low = Number(minPrice);
  let high = Number(maxPrice);
  if (!Number.isFinite(low) || !Number.isFinite(high) || low <= 0 || high <= 0 || high < low) {
    const span = Math.max(4, Math.min(20, Math.round(base * 0.3)));
    low = Math.max(1, base - span);
    high = Math.max(low + 2, base + span);
  }
  return [Math.round(low), Math.round(high)];
}

Page({
  data: {
    loading: true,
    error: "",
    found: false,
    storeName: "",
    store: null,
    openStatus: null,
    imageUrls: [],
    currentImageIndex: 0,
  },

  onLoad(options) {
    const name = decodeURIComponent((options && options.name) || "").trim();
    this.setData({ storeName: name });
    if (!name) {
      this.setData({
        loading: false,
        error: "未提供店名，无法查看详情。",
      });
      return;
    }
    this.loadStoreDetail(name);
  },

  onSwiperChange(e) {
    const index = Number(e && e.detail && e.detail.current);
    this.setData({ currentImageIndex: Number.isFinite(index) ? index : 0 });
  },

  onPreviewImage(e) {
    const index = Number(e.currentTarget.dataset.index || 0);
    const urls = this.data.imageUrls || [];
    if (!urls.length) return;
    wx.previewImage({
      current: urls[Math.max(0, Math.min(index, urls.length - 1))],
      urls,
    });
  },

  onCallStore() {
    const phone = String((this.data.store && this.data.store.phone) || "").split("/")[0].trim();
    if (!phone) {
      wx.showToast({ title: "暂无电话", icon: "none" });
      return;
    }
    wx.makePhoneCall({ phoneNumber: phone });
  },

  async loadStoreDetail(name) {
    this.setData({ loading: true, error: "", found: false, store: null, openStatus: null, imageUrls: [] });
    try {
      const res = await fetchStoreDetail(name);
      if (!res || !res.found || !res.store) {
        this.setData({
          loading: false,
          found: false,
          error: (res && res.message) || "未找到该商家详情。",
        });
        return;
      }

      const rawStore = res.store || {};
      const [avgPriceMin, avgPriceMax] = derivePriceBand(rawStore.avgPrice, rawStore.avgPriceMin, rawStore.avgPriceMax);
      const openStatusRaw = rawStore.businessStatus || computeOpenStatus(rawStore.openHours || "");
      const openStatus = {
        status: String(openStatusRaw.code || openStatusRaw.status || "unknown"),
        label: String(openStatusRaw.label || "营业时间待补充"),
        detail: String(openStatusRaw.detail || ""),
      };
      const imageUrls = normalizeImageUrls(rawStore.imageUrls);

      this.setData({
        loading: false,
        found: true,
        store: {
          ...rawStore,
          avgPrice: Number(rawStore.avgPrice) || 0,
          avgPriceMin,
          avgPriceMax,
          phone: String(rawStore.phone || "").trim(),
        },
        openStatus,
        imageUrls,
        currentImageIndex: 0,
      });
    } catch (err) {
      this.setData({
        loading: false,
        found: false,
        error: (err && err.message) || "详情请求失败，请稍后重试。",
      });
    }
  },
});
