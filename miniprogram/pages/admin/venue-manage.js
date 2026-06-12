const app = getApp();
const perm = require('../../utils/permission');

Page({
  data: {
    clubId: null,
    venues: [],
    loading: false,
  },

  onLoad(options) {
    if (!perm.requireClubAdmin()) return;
    const clubId = options.club_id || perm.getManagedClubIds()[0];
    if (!clubId) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      return wx.navigateBack();
    }
    this.setData({ clubId: parseInt(clubId) });
    this.loadVenues();
  },

  onShow() {
    if (this.data.clubId) this.loadVenues();
  },

  async loadVenues() {
    this.setData({ loading: true });
    try {
      const res = await app.request({ url: `/clubs/${this.data.clubId}/venues` });
      this.setData({ venues: res || [], loading: false });
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  onCreate() {
    wx.navigateTo({ url: `/pages/publish/venue-manage?club_id=${this.data.clubId}` });
  },

  onEdit(e) {
    const venueId = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/publish/venue-manage?club_id=${this.data.clubId}&venue_id=${venueId}` });
  },

  onSlotManage(e) {
    const venueId = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/publish/slot-manage?club_id=${this.data.clubId}&venue_id=${venueId}` });
  },

  onPullDownRefresh() {
    this.loadVenues().then(() => wx.stopPullDownRefresh());
  },
});
