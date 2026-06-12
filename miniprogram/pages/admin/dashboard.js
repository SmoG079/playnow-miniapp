const app = getApp();
const perm = require('../../utils/permission');

Page({
  data: {
    managedClubs: [],
    selectedClubIndex: 0,
    stats: null,
    loading: false,
  },

  onLoad() {
    if (!perm.isClubAdmin()) {
      wx.showToast({ title: '无权限访问', icon: 'none' });
      return wx.switchTab({ url: '/pages/home/index' });
    }
    this.setData({ managedClubs: perm.getManagedClubIds() });
    this.loadStats();
  },

  onShow() {
    if (perm.isClubAdmin()) {
      this.setData({ managedClubs: perm.getManagedClubIds() });
      this.loadStats();
    }
  },

  async loadStats() {
    const clubId = this.data.managedClubs[this.data.selectedClubIndex];
    if (!clubId) return;
    this.setData({ loading: true });
    try {
      const stats = await app.request({ url: `/clubs/${clubId}/stats` });
      this.setData({ stats, loading: false });
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  onClubChange(e) {
    this.setData({ selectedClubIndex: e.detail.value });
    this.loadStats();
  },

  onMenuTap(e) {
    const page = e.currentTarget.dataset.page;
    const clubId = this.data.managedClubs[this.data.selectedClubIndex];
    if (page) {
      wx.navigateTo({ url: `${page}?club_id=${clubId}` });
    }
  },

  onPullDownRefresh() {
    this.loadStats().then(() => wx.stopPullDownRefresh());
  },
});
