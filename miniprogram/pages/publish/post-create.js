const app = getApp();

Page({
  data: {
    title: '',
    matchMode: 'free',  // free | venue
    clubIndex: -1,
    clubIds: [],
    clubNames: [],
    venueIndex: -1,
    venueIds: [],
    venueNames: [],
    sportType: '',
    linkedVenueId: null,
    linkedBookingId: null,
    linkedVenueName: '',
    linkedSlot: '',
    preferredDate: '',
    preferredStart: '',
    preferredEnd: '',
    playersNeeded: '1',
    price: '',
    levelMin: 0,
    levelMax: 0,
    levelOptions: ['不限', '1.0', '1.5', '2.0', '2.5', '3.0', '3.5', '4.0', '4.5', '5.0', '5.5', '6.0', '6.5', '7.0'],
    description: '',
    notes: '',
    images: [],
    documents: [],
    approvalRequired: false,
    loading: false,
  },

  onShow() {
    if (!app.requireLogin({ redirect: '/pages/publish/post-create' })) return;
    this.loadClubs();
    // Check globalData for booking return (from confirm page via switchTab)
    const info = app.globalData._bookingReturn;
    if (info) {
      app.globalData._bookingReturn = null;
      this.setData({
        linkedBookingId: info.booking_id,
        linkedVenueId: info.venue_id,
        linkedVenueName: info.venue_name,
        linkedSlot: `${info.slot_date} ${info.slot_start}-${info.slot_end}`,
        preferredDate: info.slot_date || '',
        preferredStart: info.slot_start || '',
        preferredEnd: info.slot_end || '',
      });
    }
  },

  async loadClubs() {
    try {
      const managedIds = app.globalData.managedClubIds || [];
      if (managedIds.length === 0) {
        this.setData({ clubIds: [], clubNames: [], clubIndex: -1 });
        return;
      }
      const res = { items: await app.listAll('/clubs') };
      const clubs = (res.items || []).filter(c => managedIds.includes(c.id));
      if (clubs.length === 0) {
        this.setData({ clubIds: [], clubNames: [], clubIndex: -1 });
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
  onPriceChange(e) { this.setData({ price: e.detail.value }); },
  onClubChange(e) {
    const clubIndex = parseInt(e.detail.value);
    if (clubIndex !== this.data.clubIndex) this.onClearBooking();
    this.setData({ clubIndex });
  },

  onModeSwitch(e) {
    const mode = e.currentTarget.dataset.mode;
    this.setData({ matchMode: mode });
    if (mode === 'free') this.onClearBooking();
  },

  // 定场约球：跳转到场地预约页面
  onGoBookVenue() {
    if (this.data.clubIndex < 0) {
      wx.showToast({ title: '请先选择俱乐部', icon: 'none' });
      return;
    }
    const clubId = this.data.clubIds[this.data.clubIndex];
    wx.navigateTo({
      url: `/pages/booking/venue-detail?id=${clubId}&return_mode=post`,
    });
  },

  onClearBooking() {
    this.setData({
      linkedVenueId: null, linkedBookingId: null,
      linkedVenueName: '', linkedSlot: '',
      preferredDate: '', preferredStart: '', preferredEnd: '',
    });
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
    const start = levelOptions[levelMin || 1];
    const end = levelOptions[levelMax];
    if (levelMin === levelMax) return start;
    return `${start}-${end}`;
  },

  onApprovalChange(e) {
    this.setData({ approvalRequired: e.detail.value });
  },

  async onAddDocument() {
    if (this.data.documents.length >= 5) return wx.showToast({ title: '最多5个附件', icon: 'none' });
    try {
      const res = await wx.chooseMessageFile({
        count: 1,
        type: 'file',
        extension: ['pdf'],
      });
      const file = res.tempFiles[0];
      if (!file) return;
      if (file.size > 10 * 1024 * 1024) return wx.showToast({ title: '附件不能超过10MB', icon: 'none' });
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

  // Image upload
  chooseImage() {
    const remain = 6 - this.data.images.length;
    if (remain <= 0) return;
    wx.chooseImage({ count: remain, sizeType: ['compressed'], success: (res) => {
      this.setData({ images: [...this.data.images, ...res.tempFilePaths] });
    }});
  },
  removeImage(e) {
    const idx = e.currentTarget.dataset.idx;
    const imgs = this.data.images.filter((_, i) => i !== idx);
    this.setData({ images: imgs });
  },
  previewImage(e) {
    wx.previewImage({ current: e.currentTarget.dataset.url, urls: this.data.images });
  },
  async uploadImages() {
    const urls = [];
    for (const path of this.data.images) {
      if (path.startsWith('http')) { urls.push(path); continue; }
      const res = await app.uploadFile(path);
      urls.push(res.url);
    }
    return urls;
  },

  async onSubmit() {
    if (this.data.loading) return;
    if (!app.requireLogin({ redirect: '/pages/publish/post-create' })) return;
    if (!this.data.title) {
      return wx.showToast({ title: '请输入标题', icon: 'none' });
    }
    if (this.data.matchMode === 'venue' && this.data.clubIndex === -1) {
      return wx.showToast({ title: '定场约球请选择俱乐部', icon: 'none' });
    }
    if (this.data.matchMode === 'venue' && !this.data.linkedBookingId) {
      return wx.showToast({ title: '请先订场并关联预约', icon: 'none' });
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
    const playersNeeded = Number(this.data.playersNeeded);
    if (!Number.isInteger(playersNeeded) || playersNeeded < 1) {
      return wx.showToast({ title: '人数至少为 1', icon: 'none' });
    }

    this.setData({ loading: true });
    try {
      const images = await this.uploadImages();
      await app.request({
        url: '/posts',
        method: 'POST',
        data: {
          club_id: this.data.matchMode === 'venue' ? this.data.clubIds[this.data.clubIndex] : null,
          title: this.data.title,
          preferred_date: this.data.preferredDate,
          preferred_start: this.data.preferredStart,
          preferred_end: this.data.preferredEnd,
          players_needed: playersNeeded,
          price: priceNum,
          level_required: this._formatLevelRange(),
          description: this.data.description || null,
          notes: this.data.notes || null,
          venue_id: this.data.linkedVenueId || null,
          booking_id: this.data.linkedBookingId || null,
          documents: this.data.documents.length > 0 ? this.data.documents : null,
          images: images.length > 0 ? images : null,
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
