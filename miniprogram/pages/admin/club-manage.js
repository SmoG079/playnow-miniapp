const app = getApp();
const perm = require('../../utils/permission');

Page({
  data: {
    clubs: [],
    loading: false,
  },

  onLoad() {
    if (!perm.isClubAdmin()) {
      return wx.switchTab({ url: '/pages/home/index' });
    }
    this.loadClubs();
  },

  onShow() {
    if (perm.isClubAdmin()) this.loadClubs();
  },

  async loadClubs() {
    this.setData({ loading: true });
    try {
      const clubIds = perm.getManagedClubIds();
      const clubs = [];
      for (const id of clubIds) {
        try {
          const club = await app.request({ url: `/clubs/${id}` });
          clubs.push(club);
        } catch (e) {
          console.error(e);
        }
      }
      this.setData({ clubs, loading: false });
    } catch (e) {
      console.error(e);
      this.setData({ loading: false });
    }
  },

  onCreate() {
    wx.navigateTo({ url: '/pages/publish/club-create' });
  },

  onEdit(e) {
    const clubId = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/publish/club-create?club_id=${clubId}&mode=edit` });
  },

  onPullDownRefresh() {
    this.loadClubs().then(() => wx.stopPullDownRefresh());
  },
});
