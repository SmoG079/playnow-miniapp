const app = getApp();

Page({
  data: {
    clubId: null,
    club: null,
    venues: [],
    loading: false,
    isAdmin: false,
  },

  onLoad(options) {
    this.setData({ clubId: options.id });
    this.loadClub();
  },

  onShow() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 1 });
    }
  },

  async loadClub() {
    this.setData({ loading: true });
    try {
      const club = await app.request({ url: `/clubs/${this.data.clubId}` });
      this.setData({
        club,
        venues: club.venues || [],
        isAdmin: app.managesClub(club.id) && app.isClubAdmin(),
      });
    } catch (e) {
      console.error('Load club failed', e);
    } finally {
      this.setData({ loading: false });
    }
  },

  onVenueTap(e) {
    const venueId = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/booking/venue-detail?id=${venueId}` });
  },

  onManageVenues() {
    wx.navigateTo({ url: '/pages/publish/venue-manage' });
  },

  onManageOrders() {
    wx.navigateTo({ url: '/pages/publish/order-manage' });
  },

  onManageSlots(e) {
    const venueId = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/publish/slot-manage?venue_id=${venueId}` });
  },

  onShareAppMessage() {
    return {
      title: this.data.club?.name || '运动俱乐部',
      path: `/pages/booking/club-detail?id=${this.data.clubId}`,
    };
  },
});
