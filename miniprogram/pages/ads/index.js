Page({
  data: {
    contactWechat: "chedian_bd_01",
    adSlots: [
      {
        id: "slot-campus",
        title: "校内食堂专位",
        scene: "校内高频曝光",
        audience: "适合：食堂窗口、校内餐饮品牌",
        price: "¥199 / 周",
      },
      {
        id: "slot-west",
        title: "西门商圈专位",
        scene: "晚餐与夜宵流量位",
        audience: "适合：火锅、串串、夜宵门店",
        price: "¥299 / 周",
      },
      {
        id: "slot-light",
        title: "轻食健康专位",
        scene: "健身/清淡偏好场景",
        audience: "适合：轻食、咖啡、茶饮品牌",
        price: "¥239 / 周",
      },
    ],
  },

  onCopyContact() {
    wx.setClipboardData({
      data: this.data.contactWechat,
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
});
