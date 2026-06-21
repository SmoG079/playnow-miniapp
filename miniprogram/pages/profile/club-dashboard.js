const app = getApp();

Page({
  data: {
    club: null,
    stats: null,
    venues: [],
    loading: false,
  },

  async onShow() {
    await app.fetchUserInfo();
    const clubIds = app.globalData.managedClubIds || [];
    if (clubIds.length === 0) {
      wx.showToast({ title: '暂无管理权限', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 1500);
      return;
    }
    this.loadDashboard(clubIds[0]);
  },

  async loadDashboard(clubId) {
    this.setData({ loading: true });
    try {
      const [club, stats] = await Promise.all([
        app.request({ url: `/clubs/${clubId}` }),
        app.request({ url: `/clubs/${clubId}/stats` }),
      ]);
      this.setData({
        club,
        stats,
        venues: club.venues || [],
      });
    } catch (e) {
      console.error('Load dashboard failed', e);
    } finally {
      this.setData({ loading: false });
    }
  },

  onManageVenues() {
    wx.navigateTo({ url: '/pages/publish/venue-manage' });
  },

  onManageOrders() {
    wx.navigateTo({ url: '/pages/publish/order-manage' });
  },

  onManageSlots(e) {
    const vid = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/publish/slot-manage?venue_id=${vid}` });
  },

  onEditClub() {
    wx.showToast({ title: '编辑功能即将上线', icon: 'none' });
  },
});
