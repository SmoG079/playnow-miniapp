const app = getApp();

Page({
  data: {
    clubId: null,
    club: null,
    venues: [],
    rows: [],
    displayVenues: [],
    displayRows: [],
    selectedDate: '',
    dateOptions: [],
    selectedSlots: [],
    totalPrice: 0,
    selectedDuration: '',
    loading: false,
    selectedInfo: null,
  },

  onLoad(options) {
    const sysInfo = wx.getSystemInfoSync();
    this.setData({
      clubId: options.id || options.club_id,
      statusBarHeight: sysInfo.statusBarHeight || 0,
    });
    this.initDates();
    this.loadClub();
  },

  initDates() {
    const dates = [];
    const today = new Date();
    for (let i = 0; i < 3; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() + i);
      const month = d.getMonth() + 1;
      const day = d.getDate();
      dates.push({
        value: this.formatDate(d),
        label: i === 0 ? '今天' : i === 1 ? '明天' : `${month}月${day}日`,
        weekday: ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()],
        shortDate: `${String(month).padStart(2, '0')}/${String(day).padStart(2, '0')}`,
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

  async loadClub() {
    try {
      const club = await app.request({ url: `/clubs/${this.data.clubId}` });
      if (!club.images || club.images.length === 0) {
        club.images = club.cover_image ? [club.cover_image] : ['/images/default-venue.png'];
      }
      const isClubAdmin = app.managesClub(club.id);
      this.setData({ club, isClubAdmin });
      this.loadSlots(this.data.selectedDate);
    } catch (e) {
      console.error('Load club failed', e);
    }
  },

  async loadSlots(date) {
    this.setData({ loading: true, selectedInfo: null });
    try {
      const venue = this.data.venues[this.data.currentVenueIndex];
      const venueParam = venue ? `&venue_id=${venue.id}` : '';
      const res = await app.request({
        url: `/clubs/${this.data.clubId}/venue-slots?date=${date}${venueParam}`,
      });
      const venues = res.venues || [];
      const rows = res.rows || [];
      const currentVenueIndex = this.data.showVenueSwitcher ? this.data.currentVenueIndex : 0;
      this.setData({
        venues,
        rows,
        showVenueSwitcher: venues.length > 1,
        currentVenueIndex: Math.min(currentVenueIndex, Math.max(0, venues.length - 1)),
        displayVenues: [venues[0]],
        displayRows: this._filterRows(rows, 0),
      });
      // Clear any previous selection flags
      const groups = (res || []).map(g => ({
        ...g,
        slots: g.slots.map(s => ({ ...s, _sel: false })),
      }));
      this.setData({ slotGroups: groups });
    } catch (e) {
      console.error('Load slots failed', e);
      wx.showToast({ title: '加载场次失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  _filterRows(rows, venueIndex) {
    return rows.map(row => ({
      ...row,
      cells: row.cells[venueIndex] ? [row.cells[venueIndex]] : [],
    }));
  },

  onSwitchVenue() {
    if (this.data.venues.length <= 1) return;
    const names = this.data.venues.map(v => v.name);
    wx.showActionSheet({
      itemList: names,
      success: (res) => {
        const idx = res.tapIndex;
        this.setData({
          currentVenueIndex: idx,
          displayVenues: [this.data.venues[idx]],
          displayRows: this._filterRows(this.data.rows, idx),
          selectedSlots: [],
          totalPrice: 0,
          selectedDuration: '',
        });
      },
    });
  },

  markSelectedRows(rows, selectedSlots) {
    const selectedIds = new Set(selectedSlots.map(s => s.slot_id));
    return rows.map(row => ({
      ...row,
      cells: row.cells.map(cell => ({
        ...cell,
        isSelected: selectedIds.has(cell.slot_id),
      })),
    }));
  },

  onBook() {
    const slots = this.data.selectedSlots;
    if (slots.length === 0) {
      wx.showToast({ title: '请先选择时段', icon: 'none' });
      return;
    }

    const sorted = slots.slice().sort((a, b) => a.start_time.localeCompare(b.start_time));
    const first = sorted[0];
    const last = sorted[sorted.length - 1];
    const venue = this.data.displayVenues[0] || {};
    const slotIds = sorted.map(s => s.slot_id).join(',');

    wx.navigateTo({
      url: `/pages/booking/confirm?slot_ids=${slotIds}&venue_id=${first.venue_id}&price=${this.data.totalPrice}&date=${first.date}&start=${first.start_time}&end=${last.end_time}&club_name=${encodeURIComponent((this.data.club || {}).name || '')}&venue_name=${encodeURIComponent(venue.name || '')}`,
    });
  },

  onDateChange(e) {
    const date = e.currentTarget.dataset.date;
    this.setData({ selectedDate: date, selectedSlots: [], totalPrice: 0, selectedDuration: '' });
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
