const app = getApp();

Page({
  data: {
    clubId: null,
    club: null,
    venues: [],
    rows: [],
    selectedDate: '',
    dateOptions: [],
    selectedSlots: [],
    totalPrice: 0,
    selectedDuration: '',
    loading: false,
    currentImage: 0,
  },

  onLoad(options) {
    this.setData({ clubId: options.id || options.club_id });
    this.initDates();
    this.loadClub();
  },

  initDates() {
    const dates = [];
    const today = new Date();
    for (let i = 0; i < 14; i++) {
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
    this.setData({
      dateOptions: dates,
      selectedDate: dates[0].value,
    });
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
      // Ensure images is an array
      if (!club.images) club.images = club.cover_image ? [club.cover_image] : [];
      this.setData({ club });
      this.loadSlots(this.data.selectedDate);
    } catch (e) {
      console.error('Load club failed', e);
    }
  },

  async loadSlots(date) {
    this.setData({ loading: true, selectedSlots: [], totalPrice: 0, selectedDuration: '' });
    try {
      const res = await app.request({
        url: `/clubs/${this.data.clubId}/venue-slots?date=${date}`,
      });
      this.setData({
        venues: res.venues || [],
        rows: this.markSelectedRows(res.rows || [], []),
      });
    } catch (e) {
      console.error('Load slots failed', e);
      wx.showToast({ title: '加载场次失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
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

  onDateChange(e) {
    const date = e.currentTarget.dataset.date;
    this.setData({ selectedDate: date, selectedSlots: [], totalPrice: 0, selectedDuration: '' });
    this.loadSlots(date);
  },

  onSlotTap(e) {
    const { rowIndex, colIndex } = e.currentTarget.dataset;
    const cell = this.data.rows[rowIndex].cells[colIndex];
    if (cell.status !== 'available') return;

    const alreadySelected = this.data.selectedSlots.length > 0 &&
      this.data.selectedSlots[0].slot_id === cell.slot_id;

    if (alreadySelected) {
      // Deselect
      this.setData({
        selectedSlots: [],
        totalPrice: 0,
        selectedDuration: '',
        rows: this.markSelectedRows(this.data.rows, []),
      });
    } else {
      // Select new slot (single selection only)
      const slot = {
        slot_id: cell.slot_id,
        venue_id: cell.venue_id,
        venue_name: this.data.venues.find(v => v.id === cell.venue_id)?.name || '',
        price: cell.price,
        start_time: cell.start_time,
        end_time: cell.end_time,
        date: this.data.selectedDate,
      };
      this.setData({
        selectedSlots: [slot],
        totalPrice: parseFloat(cell.price),
        selectedDuration: this._calcDuration(cell.start_time, cell.end_time),
        rows: this.markSelectedRows(this.data.rows, [slot]),
      });
    }
  },

  _calcDuration(start, end) {
    const [sh, sm] = start.split(':').map(Number);
    const [eh, em] = end.split(':').map(Number);
    const minutes = (eh * 60 + em) - (sh * 60 + sm);
    if (minutes >= 60) {
      const h = Math.floor(minutes / 60);
      const m = minutes % 60;
      return m > 0 ? `${h}.${m / 60}`.replace(/0+$/, '').replace(/\.$/, '') + '小时' : `${h}小时`;
    }
    return `${minutes}分钟`;
  },

  onCancel() {
    this.setData({
      selectedSlots: [],
      totalPrice: 0,
      selectedDuration: '',
      rows: this.markSelectedRows(this.data.rows, []),
    });
  },

  onBook() {
    const slots = this.data.selectedSlots;
    if (slots.length === 0) {
      wx.showToast({ title: '请先选择时段', icon: 'none' });
      return;
    }

    const slot = slots[0];
    wx.navigateTo({
      url: `/pages/booking/confirm?slot_id=${slot.slot_id}&venue_id=${slot.venue_id}&price=${slot.price}&date=${slot.date}&start=${slot.start_time}&end=${slot.end_time}`,
    });
  },

  onPhoneTap() {
    const phone = this.data.club?.contact_phone;
    if (phone) {
      wx.makePhoneCall({ phoneNumber: phone });
    }
  },

  onImageChange(e) {
    this.setData({ currentImage: e.detail.current });
  },

  onNavigateBack() {
    wx.navigateBack();
  },

  onShareAppMessage() {
    return {
      title: `${(this.data.club && this.data.club.name) || '场地'} - 来订场吧`,
      path: `/pages/booking/venue-detail?id=${this.data.clubId}`,
    };
  },
});
