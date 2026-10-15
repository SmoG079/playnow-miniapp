const tabs = require("./tabs.js");
Component({
  data: { selected: 0, unread: "", safeBottom: 0, hidden: false, tabs },
  lifetimes: { attached() { this.sync(); } },
  pageLifetimes: { show() { this.sync(); } },
  methods: {
    sync() {
      const app = getApp();
      const pages = getCurrentPages();
      const route = app?.globalData?.playnowTabPath || pages[pages.length - 1]?.route;
      const selected = tabs.findIndex(tab => tab.pagePath === route);
      const count = app?.globalData?.playnowUnread || 0;
      const window = wx.getWindowInfo();
      const safeBottom = Math.max(0, window.screenHeight - (window.safeArea?.bottom ?? window.screenHeight));
      this.setData({ safeBottom, ...(selected >= 0 ? { selected } : {}), unread: count > 99 ? "99+" : count ? String(count) : "" });
    },
    switchTab(event) {
      const index = Number(event.currentTarget.dataset.index);
      const tab = tabs[index];
      if (!tab) return;
      if ((index === 2 || index === 4) && !wx.getStorageSync("access_token")) {
        wx.navigateTo({ url: "/pages/common/login?redirect=" + encodeURIComponent("/" + tab.pagePath) });
        return;
      }
      const pages = getCurrentPages();
      const previous = pages[pages.length - 1]?.route;
      if (previous === tab.pagePath) { this.setData({ selected: index }); return; }
      const app = getApp();
      app.globalData ||= {};
      const version = (app.globalData.playnowTabNavigation || 0) + 1;
      app.globalData.playnowTabNavigation = version;
      app.globalData.playnowTabPath = tab.pagePath;
      this.setData({ selected: index });
      wx.switchTab({
        url: "/" + tab.pagePath,
        fail: () => {
          if (app.globalData.playnowTabNavigation !== version) return;
          app.globalData.playnowTabPath = previous;
          this.sync();
        }
      });
    }
  }
});
