const app = getApp();
const perm = require('../../utils/permission');

Page({
  data: {
    clubId: null,
    club: null,
    stats: null,
    imgList: [],
    loading: false,
    managedClubs: [],
    clubIndex: 0,
    // Venue edit modal
    showVenueModal: false,
    editingVenue: null,
    venueForm: { name: '', price_per_hour: '' },
    priceRules: [],
    venues: [],
  },

  async onLoad(options) {
    if (!perm.requireClubAdmin()) return;
    const managedIds = perm.getManagedClubIds();
    if (managedIds.length === 0) {
      wx.showToast({ title: '您还没有管理的俱乐部', icon: 'none' });
      return;
    }
    try {
      const clubs = { items: await app.listAll('/clubs') };
      const managedClubs = (clubs.items || []).filter(c => managedIds.includes(c.id)).map(c => ({ id: c.id, name: c.name }));
      this.setData({ managedClubs });
      if (!managedClubs.length) return;
      let clubId = options.club_id ? parseInt(options.club_id) : managedClubs[0].id;
      const idx = managedClubs.findIndex(c => c.id === clubId);
      this.setData({ clubId: idx >= 0 ? clubId : managedClubs[0].id, clubIndex: idx >= 0 ? idx : 0 });
      this.loadData();
    } catch (e) { console.error(e); }
  },

  onShow() {
    if (this.data.clubId) this.loadData();
  },

  onPullDownRefresh() { return this.loadData().finally(() => wx.stopPullDownRefresh()); },
  onPhoneTap() {
    const phone = this.data.club && this.data.club.contact_phone;
    if (phone) wx.makePhoneCall({ phoneNumber: phone });
  },
  onVenueList() { wx.navigateTo({ url: `/pages/admin/venue-manage?club_id=${this.data.clubId}` }); },
  onStatistics() { wx.navigateTo({ url: '/pages/admin/dashboard' }); },

  async loadData() {
    if (!this.data.clubId) return;
    this.setData({ loading: true });
    try {
      const [club, stats] = await Promise.all([
        app.request({ url: `/clubs/${this.data.clubId}` }),
        app.request({ url: `/clubs/${this.data.clubId}/stats` }),
      ]);
      const imgList = (club.images && club.images.length) ? club.images : (club.cover_image ? [club.cover_image] : ['/images/default-venue.png']);
      this.setData({ club, stats, imgList, venues: club.venues || [] });
    } catch (e) {
      wx.showToast({ title: '加载失败', icon: 'none' });
    } finally { this.setData({ loading: false }); }
  },

  onClubChange(e) {
    const club = this.data.managedClubs[e.detail.value];
    this.setData({ clubId: club.id, clubIndex: e.detail.value });
    this.loadData();
  },

  onEditClub() { wx.navigateTo({ url: `/pages/publish/club-create?club_id=${this.data.clubId}&mode=edit` }); },
  onOrderManage() { wx.navigateTo({ url: `/pages/admin/order-manage?club_id=${this.data.clubId}` }); },
  onCreateClub() { wx.navigateTo({ url: '/pages/publish/club-create' }); },

  onAddVenue() {
    wx.navigateTo({ url: `/pages/publish/venue-manage?club_id=${this.data.clubId}` });
  },
  onEditVenue(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/publish/venue-manage?club_id=${this.data.clubId}&venue_id=${id}` });
  },
});
