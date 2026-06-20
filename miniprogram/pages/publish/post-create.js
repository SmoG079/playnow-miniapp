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
    price: '',
    levelMin: 0,
    levelMax: 13,
    levelOptions: ['不限', '1.0', '1.5', '2.0', '2.5', '3.0', '3.5', '4.0', '4.5', '5.0', '5.5', '6.0', '6.5', '7.0'],
    description: '',
    notes: '',
    documents: [],
    approvalRequired: false,
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
  onLevelMinChange(e) {
    let min = parseInt(e.detail.value);
    let max = this.data.levelMax;
    if (min > max) {
      max = min;
    }
    this.setData({ levelMin: min, levelMax: max });
  },
  onLevelMaxChange(e) {
    let max = parseInt(e.detail.value);
    let min = this.data.levelMin;
    if (max < min) {
      min = max;
    }
    this.setData({ levelMin: min, levelMax: max });
  },

  _formatLevelRange() {
    const { levelMin, levelMax, levelOptions } = this.data;
    if (levelMin === 0 && levelMax === 0) return null;
    const start = levelOptions[levelMin];
    const end = levelOptions[levelMax];
    if (levelMin === levelMax) return start;
    return `${start}-${end}`;
  },

  onApprovalChange(e) {
    this.setData({ approvalRequired: e.detail.value });
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
    if (!this.data.preferredDate) {
      return wx.showToast({ title: '请选择日期', icon: 'none' });
    }
    if (!this.data.preferredStart || !this.data.preferredEnd) {
      return wx.showToast({ title: '请选择开始和结束时间', icon: 'none' });
    }
    if (this.data.preferredEnd <= this.data.preferredStart) {
      return wx.showToast({ title: '结束时间必须晚于开始时间', icon: 'none' });
    }
    if (this.data.price === '' || this.data.price === null || this.data.price === undefined) {
      return wx.showToast({ title: '请填写人均费用，0 表示免费', icon: 'none' });
    }
    const priceNum = parseFloat(this.data.price);
    if (isNaN(priceNum) || priceNum < 0) {
      return wx.showToast({ title: '费用不能为负数', icon: 'none' });
    }
    const playersNeeded = parseInt(this.data.playersNeeded) || 1;
    if (playersNeeded < 1) {
      return wx.showToast({ title: '人数至少为 1', icon: 'none' });
    }

    this.setData({ loading: true });
    try {
      await app.request({
        url: '/posts',
        method: 'POST',
        data: {
          club_id: this.data.clubIds[this.data.clubIndex],
          title: this.data.title,
          preferred_date: this.data.preferredDate,
          preferred_start: this.data.preferredStart,
          preferred_end: this.data.preferredEnd,
          players_needed: playersNeeded,
          price: priceNum,
          level_required: this._formatLevelRange(),
          description: this.data.description || null,
          notes: this.data.notes || null,
          venue_id: this.data.venueIndex > -1 ? this.data.venueIds[this.data.venueIndex] : null,
          booking_id: null,
          documents: this.data.documents.length > 0 ? this.data.documents : null,
          approval_required: this.data.approvalRequired,
        },
      });
      wx.showToast({ title: '发布成功', icon: 'success' });
      app.globalData.needRefreshFeed = true;
      setTimeout(() => wx.switchTab({ url: '/pages/home/index' }), 1500);
    } catch (e) {
      console.error(e);
      wx.showToast({ title: e?.data?.detail || '发布失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },
});
