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

  onDelete(e) {
    const venue = e.currentTarget.dataset.venue;
    wx.showModal({
      title: '确认删除',
      content: `确定要删除场地"${venue.name}"吗？`,
      confirmColor: '#f44336',
      success: (res) => {
        if (res.confirm) this.doDelete(venue.id);
      },
    });
  },

  async doDelete(venueId) {
    try {
      await app.request({
        url: `/venues/${venueId}/with-club/${this.data.clubId}`,
        method: 'DELETE',
      });
      wx.showToast({ title: '已删除', icon: 'success' });
      this.loadVenues();
    } catch (e) {
      wx.showToast({ title: '删除失败', icon: 'none' });
    }
  },

  onPullDownRefresh() {
    this.loadVenues().then(() => wx.stopPullDownRefresh());
  },
});
