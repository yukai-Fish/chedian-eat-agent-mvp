const { fetchAdSlots, logAdClick } = require("../../utils/api");
const { getCurrentIdentity } = require("../../utils/identity");

const TAB_PAGES = new Set(["/pages/index/index", "/pages/ads/index", "/pages/profile/index"]);
const FALLBACK_CONTACT = "chedian_bd_01";
const FALLBACK_SLOTS = [
  {
    id: "fallback-campus",
    title: "校内食堂精选位",
    subtitle: "面向正在搜索校园餐的学生",
    scene: "校内高频曝光",
    audience: "适合：食堂窗口、校内餐饮品牌",
    priceLabel: "¥199 / 周",
    imageUrl: "/assets/tabbar/ginkgo-gold.png",
    landingType: "copy_wechat",
    landingValue: FALLBACK_CONTACT,
  },
  {
    id: "fallback-west-gate",
    title: "西门商圈高转化位",
    subtitle: "晚餐和夜宵时段重点曝光",
    scene: "夜间高转化流量",
    audience: "适合：火锅、烧烤、夜宵门店",
    priceLabel: "¥299 / 周",
    imageUrl: "/assets/tabbar/xiaohui.png",
    landingType: "copy_wechat",
    landingValue: FALLBACK_CONTACT,
  },
  {
    id: "fallback-light-food",
    title: "轻食咖啡白领位",
    subtitle: "覆盖低脂、下午茶、学习场景",
    scene: "轻食健身偏好场景",
    audience: "适合：轻食、咖啡、茶饮品牌",
    priceLabel: "¥239 / 周",
    imageUrl: "/assets/tabbar/ginkgo-gold.png",
    landingType: "copy_wechat",
    landingValue: FALLBACK_CONTACT,
  },
];

Page({
  data: {
    loading: false,
    error: "",
    contactWechat: FALLBACK_CONTACT,
    adSlots: [],
    currentIndex: 0,
  },

  onShow() {
    this.identity = getCurrentIdentity();
    this.loadAds();
  },

  async loadAds() {
    this.setData({ loading: true, error: "" });
    try {
      const res = await fetchAdSlots(12);
      const items = Array.isArray(res && res.items) ? res.items : [];
      if (!items.length) {
        this.setData({
          loading: false,
          adSlots: FALLBACK_SLOTS,
          currentIndex: 0,
          contactWechat: String((res && res.contactWechat) || FALLBACK_CONTACT).trim() || FALLBACK_CONTACT,
        });
        return;
      }
      this.setData({
        loading: false,
        adSlots: items,
        currentIndex: 0,
        contactWechat: String((res && res.contactWechat) || FALLBACK_CONTACT).trim() || FALLBACK_CONTACT,
      });
    } catch (_err) {
      // Backend ads APIs may not be deployed yet. Keep the page usable with local fallback slots.
      this.setData({
        loading: false,
        error: "",
        adSlots: FALLBACK_SLOTS,
        currentIndex: 0,
        contactWechat: FALLBACK_CONTACT,
      });
    }
  },

  onSwiperChange(e) {
    const idx = Number(e && e.detail && e.detail.current);
    this.setData({ currentIndex: Number.isFinite(idx) ? idx : 0 });
  },

  onCopyContact() {
    wx.setClipboardData({
      data: String(this.data.contactWechat || FALLBACK_CONTACT),
      success: () => {
        wx.showToast({ title: "商务微信已复制", icon: "success" });
      },
      fail: () => {
        wx.showToast({ title: "复制失败，请稍后重试", icon: "none" });
      },
    });
  },

  onGoInquiry() {
    wx.switchTab({
      url: "/pages/index/index",
    });
  },

  onTapSlide(e) {
    const index = Number(e && e.currentTarget && e.currentTarget.dataset && e.currentTarget.dataset.index);
    const slot = this.data.adSlots[index];
    if (!slot) return;
    this.reportClick(slot);
    this.handleLanding(slot);
  },

  reportClick(slot) {
    const identity = this.identity || getCurrentIdentity();
    logAdClick({
      slotId: String(slot.id || ""),
      uid: identity.uid,
      anonymousId: identity.anonymousId,
      userId: identity.userId,
      source: "miniprogram_ads",
    }).catch(() => {
      // Keep UX smooth when logging fails.
    });
  },

  handleLanding(slot) {
    const type = String(slot.landingType || "none").trim();
    const value = String(slot.landingValue || "").trim();

    if (type === "store_detail" && value) {
      wx.navigateTo({
        url: `/pages/store-detail/index?name=${encodeURIComponent(value)}`,
      });
      return;
    }

    if (type === "miniprogram_path" && value) {
      const path = value.startsWith("/") ? value : `/${value}`;
      const pure = path.split("?")[0];
      if (TAB_PAGES.has(pure)) {
        wx.switchTab({ url: pure });
      } else {
        wx.navigateTo({ url: path });
      }
      return;
    }

    if (type === "copy_wechat" && value) {
      wx.setClipboardData({
        data: value,
        success: () => wx.showToast({ title: "联系方式已复制", icon: "success" }),
      });
      return;
    }

    if (type === "external_web" && value) {
      wx.setClipboardData({
        data: value,
        success: () => wx.showToast({ title: "链接已复制，请在浏览器打开", icon: "none" }),
      });
      return;
    }

    wx.showToast({
      title: "可联系商务微信了解投放",
      icon: "none",
    });
  },
});
