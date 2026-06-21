const app = getApp();

Page({
  data: {
    venueId: null,
    venue: null,
    selectedDate: '',
    dateOptions: [],
    slotGroups: [],
    loading: false,
    selectedInfo: null,
  },

  onLoad(options) {
    this.setData({ venueId: options.id });
    this.initDates();
    this.loadVenue();
  },

  initDates() {
    const dates = [];
    const today = new Date();
    for (let i = 0; i < 3; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() + i);
      dates.push({
        value: this.formatDate(d),
        label: i === 0 ? '今天' : i === 1 ? '明天' : `${d.getMonth() + 1}/${d.getDate()}`,
        weekday: ['日', '一', '二', '三', '四', '五', '六'][d.getDay()],
      });
    }
    this.setData({ dateOptions: dates, selectedDate: dates[0].value });
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
    this.setData({ loading: true, selectedInfo: null });
    try {
      const res = await app.request({
        url: `/venues/${this.data.venueId}/slots?date_from=${date}&date_to=${date}`,
      });
      // Clear any previous selection flags
      const groups = (res || []).map(g => ({
        ...g,
        slots: g.slots.map(s => ({ ...s, _sel: false })),
      }));
      this.setData({ slotGroups: groups });
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
    const allSlots = this._flatSlots();
    if (slot.status !== 'available') return;

    const idx = allSlots.findIndex(s => s.id === slot.id);
    if (idx === -1 || idx >= allSlots.length - 1) return;

    const nextSlot = allSlots[idx + 1];
    if (nextSlot.status !== 'available') {
      wx.showToast({ title: '需连续 1 小时，相邻时段不可用', icon: 'none' });
      return;
    }

    // Clear previous selection, set new pair
    const groups = this.data.slotGroups.map(g => ({
      ...g,
      slots: g.slots.map(s => ({
        ...s,
        _sel: s.id === slot.id || s.id === nextSlot.id,
      })),
    }));

    const price = parseFloat(slot.price) + parseFloat(nextSlot.price);
    this.setData({
      slotGroups: groups,
      selectedInfo: {
        slot1Id: slot.id,
        slot2Id: nextSlot.id,
        date: this.data.selectedDate,
        startTime: slot.start_time,
        endTime: nextSlot.end_time,
        price: price.toFixed(2),
      },
    });
  },

  _flatSlots() {
    const all = [];
    for (const g of this.data.slotGroups) {
      for (const s of g.slots) all.push(s);
    }
    return all;
  },

  onConfirmBooking() {
    const info = this.data.selectedInfo;
    if (!info) {
      wx.showToast({ title: '请先选择时段（1小时起订）', icon: 'none' });
      return;
    }
    wx.navigateTo({
      url: `/pages/booking/confirm?slot_id=${info.slot1Id}&slot2_id=${info.slot2Id}&venue_id=${this.data.venueId}&price=${info.price}&date=${info.date}&start=${info.startTime}&end=${info.endTime}`,
    });
  },
});
