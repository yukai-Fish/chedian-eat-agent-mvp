const { fetchStoreDetail } = require("../../utils/api");

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

function computeOpenStatus(openHoursText) {
  const parsed = parseIntervals(openHoursText);
  if (parsed.unknown) {
    return {
      status: "unknown",
      label: "营业时间待补充",
      detail: "暂缺营业时间信息，可先查看评价再决策。",
    };
  }
  if (parsed.allDay) {
    return {
      status: "open",
      label: "营业中",
      detail: "24小时营业",
    };
  }

  const now = new Date();
  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  let minLeft = Number.POSITIVE_INFINITY;
  let isOpen = false;

  for (const [start, end] of parsed.intervals) {
    const probes = [nowMinutes, nowMinutes + 24 * 60];
    for (const point of probes) {
      if (point >= start && point < end) {
        isOpen = true;
        minLeft = Math.min(minLeft, end - point);
      }
    }
  }

  if (isOpen) {
    if (minLeft <= 60) {
      return {
        status: "closing",
        label: "即将打烊",
        detail: `预计 ${Math.max(1, Math.round(minLeft))} 分钟后打烊`,
      };
    }
    return {
      status: "open",
      label: "营业中",
      detail: "当前时段可前往就餐",
    };
  }

  return {
    status: "closed",
    label: "未营业",
    detail: "当前不在营业时段，建议先看其他店。",
  };
}

Page({
  data: {
    loading: true,
    error: "",
    found: false,
    storeName: "",
    store: null,
    openStatus: null,
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

  async loadStoreDetail(name) {
    this.setData({ loading: true, error: "", found: false, store: null, openStatus: null });
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
      const openStatus = computeOpenStatus(res.store.openHours);
      this.setData({
        loading: false,
        found: true,
        store: res.store,
        openStatus,
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
