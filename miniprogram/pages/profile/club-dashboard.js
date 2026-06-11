const app = getApp();
const perm = require('../../utils/permission');

Page({
  data: {
    clubId: null,
    club: null,
    stats: null,
    loading: false,
    managedClubs: [],
  },

  onLoad(options) {
    const managed = perm.getManagedClubIds();
    this.setData({ managedClubs: managed });

    if (options.club_id) {
      this.setData({ clubId: parseInt(options.club_id) });
    } else if (managed.length === 1) {
      this.setData({ clubId: managed[0] });
    } else if (managed.length === 0) {
      wx.showToast({ title: '您还没有管理的俱乐部', icon: 'none' });
      return;
    }

    if (this.data.clubId) {
      this.loadData();
    }
  },

  onShow() {
    if (this.data.clubId) {
      this.loadData();
    }
  },

  async loadData() {
    if (!this.data.clubId) return;
    this.setData({ loading: true });
    try {
      const [club, stats] = await Promise.all([
        app.request({ url: `/clubs/${this.data.clubId}` }),
        app.request({ url: `/clubs/${this.data.clubId}/stats` }),
      ]);
      // Ensure images is an array
      if (!club.images) club.images = club.cover_image ? [club.cover_image] : [];
      this.setData({ club, stats });
    } catch (e) {
      console.error('Load club dashboard failed', e);
      wx.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  onClubChange(e) {
    const index = e.detail.value;
    const clubId = this.data.managedClubs[index];
    this.setData({ clubId });
    this.loadData();
  },

  onEditClub() {
    wx.navigateTo({
      url: `/pages/publish/club-create?club_id=${this.data.clubId}&mode=edit`,
    });
  },

  onVenueManage() {
    wx.navigateTo({
      url: `/pages/publish/venue-manage?club_id=${this.data.clubId}`,
    });
  },

  onSlotManage() {
    wx.navigateTo({
      url: `/pages/publish/slot-manage?club_id=${this.data.clubId}`,
    });
  },

  onOrderManage() {
    wx.navigateTo({
      url: `/pages/publish/order-manage?club_id=${this.data.clubId}`,
    });
  },

  onPhoneTap() {
    const phone = (this.data.club || {}).contact_phone;
    if (phone) {
      wx.makePhoneCall({ phoneNumber: phone });
    }
  },

  onCreateClub() {
    wx.navigateTo({ url: '/pages/publish/club-create' });
  },
});
