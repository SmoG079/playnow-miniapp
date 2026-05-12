const app = getApp();

Page({
  data: {
    venueId: null,
    venue: null,
    selectedDate: '',
    dateOptions: [],
    slotGroups: [],
    loading: false,
  },

  onLoad(options) {
    this.setData({ venueId: options.id });
    this.initDates();
    this.loadVenue();
  },

  initDates() {
    const dates = [];
    const today = new Date();
    for (let i = 0; i < 14; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() + i);
      dates.push({
        value: this.formatDate(d),
        label: i === 0 ? '今天' : i === 1 ? '明天' : `${d.getMonth() + 1}/${d.getDate()}`,
        weekday: ['日', '一', '二', '三', '四', '五', '六'][d.getDay()],
      });
    }
    this.setData({
      dateOptions: dates,
      selectedDate: dates[0].value,
    });
    this.loadSlots(dates[0].value);
  },

  formatDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  },

  async loadVenue() {
    try {
      const res = await app.request({ url: `/venues/${this.data.venueId}` });
      this.setData({ venue: res });
    } catch (e) {
      console.error('Load venue failed', e);
    }
  },

  async loadSlots(date) {
    this.setData({ loading: true });
    try {
      const res = await app.request({
        url: `/venues/${this.data.venueId}/slots?date_from=${date}&date_to=${date}`,
      });
      this.setData({ slotGroups: res || [] });
    } catch (e) {
      console.error('Load slots failed', e);
    } finally {
      this.setData({ loading: false });
    }
  },

  onDateChange(e) {
    const date = e.currentTarget.dataset.date;
    this.setData({ selectedDate: date });
    this.loadSlots(date);
  },

  onSlotTap(e) {
    const slot = e.currentTarget.dataset.slot;
    if (slot.status !== 'available') return;

    // Navigate to confirm page
    wx.navigateTo({
      url: `/pages/booking/confirm?slot_id=${slot.id}&venue_id=${this.data.venueId}&price=${slot.price}&date=${this.data.selectedDate}&start=${slot.start_time}&end=${slot.end_time}`,
    });
  },

  onShareAppMessage() {
    return {
      title: `${this.data.venue?.name || '场地'} - 来订场吧`,
      path: `/pages/booking/venue-detail?id=${this.data.venueId}`,
    };
  },
});
