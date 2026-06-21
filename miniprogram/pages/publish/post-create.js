const app = getApp();

Page({
  data: {
    title: '',
    clubIndex: -1,
    clubIds: [],
    clubNames: [],
    mode: 0,
    // Venue slot selection
    venues: [],
    venueIndex: -1,
    venueNames: [],
    venueSlots: [],
    slotLoading: false,
    selectedDate: '',
    dates: [],
    selectedSlots: [],
    selectedSlotInfo: null,
    // Common fields
    playersNeeded: '1',
    levelIndex: -1,
    levels: ['不限', '初级', '中级', '高级'],
    notes: '',
    loading: false,
  },

  onShow() {
    this.loadClubs();
  },

  async loadClubs() {
    try {
      const res = await app.request({ url: '/clubs?page=1&page_size=50' });
      const clubs = res.items || [];
      this.setData({
        clubIds: clubs.map(c => c.id),
        clubNames: clubs.map(c => c.name),
      });
    } catch (e) { console.error(e); }
  },

  onClubChange(e) {
    const idx = parseInt(e.detail.value);
    this.setData({ clubIndex: idx });
    this.loadVenues(this.data.clubIds[idx]);
  },

  async loadVenues(clubId) {
    if (!clubId) return;
    try {
      const res = await app.request({ url: `/clubs/${clubId}/venues` });
      const venues = res || [];
      this.setData({
        venues,
        venueNames: venues.map(v => v.name),
        venueIndex: -1,
        venueSlots: [],
        selectedSlots: [],
        selectedSlotInfo: null,
      });
    } catch (e) { console.error(e); }
  },

  onVenueChange(e) {
    const idx = parseInt(e.detail.value);
    this.setData({ venueIndex: idx, selectedSlots: [], selectedSlotInfo: null });
    this.initDates();
    if (idx > -1) this.loadSlots(this.data.dates[0]);
  },

  onModeSwitch(e) {
    this.setData({
      mode: parseInt(e.currentTarget.dataset.mode),
      selectedSlots: [],
      selectedSlotInfo: null,
    });
  },

  initDates() {
    const dates = [];
    const today = new Date();
    for (let i = 0; i < 3; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() + i);
      dates.push({
        value: this.fmtDate(d),
        label: i === 0 ? '今天' : i === 1 ? '明天' : `${d.getMonth() + 1}/${d.getDate()}`,
      });
    }
    this.setData({ dates, selectedDate: dates[0].value });
  },

  fmtDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  },

  onDateSelect(e) {
    const d = e.currentTarget.dataset.date;
    this.setData({ selectedDate: d, selectedSlots: [], selectedSlotInfo: null });
    this.loadSlots(d);
  },

  async loadSlots(date) {
    const v = this.data.venues[this.data.venueIndex];
    if (!v) return;
    this.setData({ slotLoading: true });
    try {
      const res = await app.request({
        url: `/venues/${v.id}/slots?date_from=${date}&date_to=${date}`,
      });
      const flat = [];
      for (const g of (res || [])) {
        for (const s of g.slots) flat.push({ ...s, _sel: false });
      }
      this.setData({ venueSlots: flat });
    } catch (e) { console.error(e); }
    finally { this.setData({ slotLoading: false }); }
  },

  onSlotTap(e) {
    const slot = e.currentTarget.dataset.slot;
    if (slot.status !== 'available') return;
    const idx = this.data.venueSlots.findIndex(s => s.id === slot.id);
    if (idx === -1 || idx >= this.data.venueSlots.length - 1) return;
    const next = this.data.venueSlots[idx + 1];
    if (next.status !== 'available') {
      wx.showToast({ title: '需连续 1 小时', icon: 'none' });
      return;
    }
    const price = parseFloat(slot.price) + parseFloat(next.price);
    this.setData({
      venueSlots: this.data.venueSlots.map(s => ({
        ...s, _sel: s.id === slot.id || s.id === next.id,
      })),
      selectedSlots: [slot.id, next.id],
      selectedSlotInfo: {
        slot1Id: slot.id, slot2Id: next.id,
        date: this.data.selectedDate,
        startTime: slot.start_time,
        endTime: next.end_time,
        price: price.toFixed(2),
      },
    });
  },

  onField(e) {
    this.setData({ [e.currentTarget.dataset.field]: e.detail.value });
  },
  onLevelChange(e) {
    this.setData({ levelIndex: parseInt(e.detail.value) });
  },

  async onSubmit() {
    if (!this.data.title || this.data.clubIndex === -1) {
      return wx.showToast({ title: '标题和俱乐部必填', icon: 'none' });
    }
    this.setData({ loading: true });
    try {
      const data = {
        club_id: this.data.clubIds[this.data.clubIndex],
        title: this.data.title,
        players_needed: parseInt(this.data.playersNeeded) || 1,
        level_required: this.data.levelIndex > 0 ? this.data.levels[this.data.levelIndex] : null,
        notes: this.data.notes || null,
      };
      // 订场约球: create booking + link to post
      if (this.data.mode === 1 && this.data.selectedSlotInfo) {
        const info = this.data.selectedSlotInfo;
        // Create booking first
        const booking = await app.request({
          url: '/bookings', method: 'POST',
          data: { slot_id: info.slot1Id, slot2_id: info.slot2Id },
        });
        // Pay immediately (placeholder)
        await app.request({ url: `/bookings/${booking.id}/pay`, method: 'POST' });
        data.venue_id = this.data.venues[this.data.venueIndex].id;
        data.booking_id = booking.id;
        data.preferred_date = info.date;
        data.preferred_start = info.startTime;
        data.preferred_end = info.endTime;
      }
      await app.request({ url: '/posts', method: 'POST', data });
      wx.showToast({ title: '发布成功', icon: 'success' });
      setTimeout(() => wx.switchTab({ url: '/pages/home/index' }), 1500);
    } catch (e) {
      console.error(e);
    } finally {
      this.setData({ loading: false });
    }
  },
});
