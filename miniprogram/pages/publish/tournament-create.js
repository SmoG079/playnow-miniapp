const app = getApp();
const perm = require('../../utils/permission');

Page({
  data: {
    managedClubs: [],
    clubNames: [],
    clubIndex: 0,
    form: {
      title: '',
      sport_type: '网球',
      start_time: '',
      end_time: '',
      entry_fee: '',
      max_participants: '',
      description: '',
      prize: '',
    },
    loading: false,
    images: [],
    linkedVenueId: null,
    linkedBookingId: null,
    linkedVenueName: '',
    linkedSlot: '',
  },

  onGoBookVenue() {
    const clubId = this.data.managedClubs[this.data.clubIndex];
    if (!clubId) return wx.showToast({ title: '请先选择俱乐部', icon: 'none' });
    wx.navigateTo({ url: `/pages/booking/venue-detail?id=${clubId}&return_mode=tournament` });
  },
  onClearBooking() {
    this.setData({ linkedVenueId: null, linkedBookingId: null, linkedVenueName: '', linkedSlot: '' });
  },

  chooseImage() {
    const remain = 6 - this.data.images.length;
    if (remain <= 0) return;
    wx.chooseImage({ count: remain, sizeType: ['compressed'], success: (res) => {
      this.setData({ images: [...this.data.images, ...res.tempFilePaths] });
    }});
  },
  removeImage(e) {
    const idx = e.currentTarget.dataset.idx;
    this.setData({ images: this.data.images.filter((_, i) => i !== idx) });
  },
  previewImage(e) {
    wx.previewImage({ current: e.currentTarget.dataset.url, urls: this.data.images });
  },
  async uploadImages() {
    const urls = [];
    for (const path of this.data.images) {
      if (path.startsWith('http')) { urls.push(path); continue; }
      try { const r = await app.uploadFile(path); urls.push(r.url); } catch (e) {}
    }
    return urls;
  },

  onShow() {
    const info = app.globalData._bookingReturn;
    if (info) {
      app.globalData._bookingReturn = null;
      this.setData({
        linkedBookingId: info.booking_id,
        linkedVenueId: info.venue_id,
        linkedVenueName: info.venue_name,
        linkedSlot: `${info.slot_date} ${info.slot_start}-${info.slot_end}`,
      });
    }
  },

  async onLoad() {
    if (!perm.requireClubAdmin()) return;
    const managedIds = perm.getManagedClubIds();
    if (managedIds.length === 0) {
      wx.showToast({ title: '您没有管理的俱乐部', icon: 'none' });
      return wx.navigateBack();
    }
    try {
      const res = await app.request({ url: '/clubs?page=1&page_size=50' });
      const clubs = (res.items || []).filter(c => managedIds.includes(c.id));
      this.setData({
        managedClubs: clubs.map(c => c.id),
        clubNames: clubs.map(c => c.name),
      });
    } catch (e) { console.error(e); }
    this.setDefaultTimes();
  },

  setDefaultTimes() {
    const now = new Date();
    const start = new Date(now.getTime() + 24 * 60 * 60 * 1000);
    start.setMinutes(0, 0, 0);
    const end = new Date(start.getTime() + 2 * 60 * 60 * 1000);
    this.setData({
      'form.start_time': this.formatDateTimeLocal(start),
      'form.end_time': this.formatDateTimeLocal(end),
    });
  },

  formatDateTimeLocal(date) {
    const pad = (n) => (n < 10 ? '0' + n : n);
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  },

  onClubChange(e) {
    this.setData({ clubIndex: e.detail.value });
  },

  onInputChange(e) {
    const { field } = e.currentTarget.dataset;
    this.setData({ [`form.${field}`]: e.detail.value });
  },

  parseDateTimeLocal(value) {
    // Accept both 'YYYY-MM-DDTHH:MM' and 'YYYY-MM-DD HH:MM'
    const normalized = value.replace('T', ' ');
    const match = normalized.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/);
    if (!match) return null;
    const [, y, m, d, h, min] = match;
    return new Date(`${y}-${m}-${d}T${h}:${min}:00`);
  },

  async onSubmit() {
    const { form, managedClubs, clubIndex } = this.data;
    if (!form.title.trim()) {
      return wx.showToast({ title: '请输入赛事名称', icon: 'none' });
    }
    if (!form.start_time || !form.end_time) {
      return wx.showToast({ title: '请选择时间', icon: 'none' });
    }
    const start = this.parseDateTimeLocal(form.start_time);
    const end = this.parseDateTimeLocal(form.end_time);
    if (!start || !end || end <= start) {
      return wx.showToast({ title: '结束时间必须晚于开始时间', icon: 'none' });
    }

    const entryFee = parseFloat(form.entry_fee) || 0;
    const maxParticipants = form.max_participants ? parseInt(form.max_participants) : null;

    const payload = {
      club_id: managedClubs[clubIndex],
      title: form.title.trim(),
      sport_type: form.sport_type || '网球',
      start_time: start.toISOString(),
      end_time: end.toISOString(),
      entry_fee: entryFee,
      venue_id: this.data.linkedVenueId || null,
      max_participants: maxParticipants,
      description: form.description,
      prize: form.prize,
    };

    this.setData({ loading: true });
    try {
      const images = await this.uploadImages();
      if (images.length > 0) payload.cover_image = images[0];
      const res = await app.request({
        url: '/tournaments',
        method: 'POST',
        data: payload,
      });
      wx.showToast({ title: '创建成功', icon: 'success' });
      setTimeout(() => {
        wx.redirectTo({ url: `/pages/common/tournament-detail?id=${res.id}` });
      }, 1500);
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '创建失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },
});
