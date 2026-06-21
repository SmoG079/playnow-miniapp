const app = getApp();

Page({
  data: {
    venueId: null,
    venue: null,
    slotGroups: [],
    loading: false,
    dateFrom: '',
    dateTo: '',
    startTime: '08:00',
    endTime: '22:00',
    interval: 60,
    intervalOptions: [
      { label: '60分钟', value: 60 },
      { label: '30分钟', value: 30 },
    ],
  },

  onLoad(options) {
    this.setData({ venueId: options.venue_id });
    this.loadVenue();
    this.loadSlots();
  },

  async loadVenue() {
    try {
      const venue = await app.request({ url: `/venues/${this.data.venueId}` });
      this.setData({ venue });
    } catch (e) {
      console.error('Load venue failed', e);
    }
  },

  async loadSlots() {
    this.setData({ loading: true });
    try {
      const now = new Date();
      const from = this.formatDate(now);
      const to = new Date(now);
      to.setDate(to.getDate() + 13);
      const dateTo = this.formatDate(to);

      const res = await app.request({
        url: `/venues/${this.data.venueId}/slots?date_from=${from}&date_to=${dateTo}`,
      });
      this.setData({ slotGroups: res || [] });
    } catch (e) {
      console.error('Load slots failed', e);
    } finally {
      this.setData({ loading: false });
    }
  },

  formatDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  },

  onDateFromChange(e) { this.setData({ dateFrom: e.detail.value }); },
  onDateToChange(e) { this.setData({ dateTo: e.detail.value }); },
  onStartTimeChange(e) { this.setData({ startTime: e.detail.value }); },
  onEndTimeChange(e) { this.setData({ endTime: e.detail.value }); },
  onIntervalChange(e) {
    this.setData({ interval: parseInt(e.currentTarget.dataset.value) });
  },

  async onGenerate() {
    if (!this.data.dateFrom || !this.data.dateTo) {
      return wx.showToast({ title: '请选择日期范围', icon: 'none' });
    }
    if (this.data.dateFrom > this.data.dateTo) {
      return wx.showToast({ title: '结束日期不能早于开始日期', icon: 'none' });
    }

    try {
      const res = await app.request({
        url: `/venues/${this.data.venueId}/slots/batch`,
        method: 'POST',
        data: {
          date_from: this.data.dateFrom,
          date_to: this.data.dateTo,
          start_time: this.data.startTime,
          end_time: this.data.endTime,
          interval_minutes: this.data.interval,
        },
      });
      wx.showToast({ title: res.msg || `已生成 ${res.created} 个时间段`, icon: 'success' });
      this.loadSlots();
    } catch (e) {
      console.error('Generate slots failed', e);
    }
  },

  onToggleSlot(e) {
    // P1: disabling individual slots will be implemented later
    wx.showToast({ title: '时段关闭功能即将上线', icon: 'none' });
  },

  statusLabel(s) {
    return { available: '可预约', locked: '锁定中', booked: '已预约', maintenance: '维护中' }[s] || s;
  },
});
