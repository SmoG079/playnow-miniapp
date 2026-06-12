const app = getApp();

Page({
  data: {
    title: '',
    clubIndex: -1,
    clubIds: [],
    clubNames: [],
    venueIndex: -1,
    venueIds: [],
    venueNames: [],
    sportType: '',
    preferredDate: '',
    preferredStart: '',
    preferredEnd: '',
    playersNeeded: '1',
    levelIndex: -1,
    levels: ['不限', '1.0', '1.5', '2.0', '2.5', '3.0', '3.5', '4.0', '4.5', '5.0', '5.5', '6.0', '6.5', '7.0'],
    description: '',
    notes: '',
    documents: [],
    loading: false,
  },

  onShow() {
    this.loadClubs();
  },

  async loadClubs() {
    try {
      const managedIds = app.globalData.managedClubIds || [];
      if (managedIds.length === 0) {
        wx.showToast({ title: '您没有管理的俱乐部，无法发布约球帖', icon: 'none' });
        setTimeout(() => wx.navigateBack(), 1500);
        return;
      }
      const res = await app.request({ url: '/clubs?page=1&page_size=50' });
      const clubs = (res.items || []).filter(c => managedIds.includes(c.id));
      if (clubs.length === 0) {
        wx.showToast({ title: '您没有管理的俱乐部，无法发布约球帖', icon: 'none' });
        setTimeout(() => wx.navigateBack(), 1500);
        return;
      }
      this.setData({
        clubIds: clubs.map(c => c.id),
        clubNames: clubs.map(c => c.name),
      });
    } catch (e) { console.error(e); }
  },

  onField(e) {
    this.setData({ [e.currentTarget.dataset.field]: e.detail.value });
  },
  onClubChange(e) {
    const clubIndex = parseInt(e.detail.value);
    this.setData({ clubIndex, venueIndex: -1, venueIds: [], venueNames: [] });
    this.loadVenues(clubIndex);
  },
  async loadVenues(clubIndex) {
    if (clubIndex < 0) return;
    const clubId = this.data.clubIds[clubIndex];
    try {
      const res = await app.request({ url: `/clubs/${clubId}` });
      const venues = res.venues || [];
      this.setData({
        venueIds: venues.map(v => v.id),
        venueNames: venues.map(v => v.name),
      });
    } catch (e) {
      console.error(e);
    }
  },

  onVenueChange(e) {
    this.setData({ venueIndex: parseInt(e.detail.value) });
  },
  onDateChange(e) {
    this.setData({ preferredDate: e.detail.value });
  },
  onTimeStart(e) {
    this.setData({ preferredStart: e.detail.value });
  },
  onTimeEnd(e) {
    this.setData({ preferredEnd: e.detail.value });
  },
  onLevelChange(e) {
    this.setData({ levelIndex: parseInt(e.detail.value) });
  },

  async onAddDocument() {
    try {
      const res = await wx.chooseMessageFile({
        type: 'file',
        extension: ['pdf'],
      });
      const file = res.tempFiles[0];
      wx.showLoading({ title: '上传中...' });
      const uploaded = await app.uploadFile(file.path);
      wx.hideLoading();
      const docs = this.data.documents.concat([{
        name: file.name,
        url: uploaded.url,
        size: file.size,
      }]);
      this.setData({ documents: docs });
    } catch (e) {
      wx.hideLoading();
      console.error(e);
      wx.showToast({ title: '上传失败', icon: 'none' });
    }
  },

  onRemoveDocument(e) {
    const idx = e.currentTarget.dataset.index;
    const docs = this.data.documents.filter((_, i) => i !== idx);
    this.setData({ documents: docs });
  },

  async onSubmit() {
    if (!this.data.title || this.data.clubIndex === -1) {
      return wx.showToast({ title: '标题和俱乐部必填', icon: 'none' });
    }
    this.setData({ loading: true });
    try {
      await app.request({
        url: '/posts',
        method: 'POST',
        data: {
          club_id: this.data.clubIds[this.data.clubIndex],
          title: this.data.title,
          sport_type: this.data.sportType || null,
          preferred_date: this.data.preferredDate || null,
          preferred_start: this.data.preferredStart || null,
          preferred_end: this.data.preferredEnd || null,
          players_needed: parseInt(this.data.playersNeeded) || 1,
          level_required: this.data.levelIndex > 0 ? this.data.levels[this.data.levelIndex] : null,
          description: this.data.description || null,
          notes: this.data.notes || null,
          venue_id: this.data.venueIndex > -1 ? this.data.venueIds[this.data.venueIndex] : null,
          booking_id: null,
          documents: this.data.documents.length > 0 ? this.data.documents : null,
        },
      });
      wx.showToast({ title: '发布成功', icon: 'success' });
      app.globalData.needRefreshFeed = true;
      setTimeout(() => wx.switchTab({ url: '/pages/home/index' }), 1500);
    } catch (e) {
      console.error(e);
    } finally {
      this.setData({ loading: false });
    }
  },
});
