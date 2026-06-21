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
    currentImage: 0,
    isClubAdmin: false,
    currentVenueIndex: 0,
    showVenueSwitcher: false,
    statusBarHeight: 0,
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
    this.setData({ loading: true, selectedSlots: [], totalPrice: 0, selectedDuration: '' });
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
    const { rowIndex } = e.currentTarget.dataset;
    const cell = this.data.displayRows[rowIndex].cells[0];
    if (cell.status !== 'available') return;

    const selected = this.data.selectedSlots;
    const idx = selected.findIndex(s => s.slot_id === cell.slot_id);

    if (idx >= 0) {
      // Deselect the tapped slot and any slots after it (must remain consecutive)
      const newSelected = selected.slice(0, idx);
      this._updateSelection(newSelected);
      return;
    }

    if (selected.length === 0) {
      // First selection
      this._addSlotToSelection(cell);
      return;
    }

    // Only allow extending the contiguous block by one slot at either end
    const sorted = selected.slice().sort((a, b) => a.start_time.localeCompare(b.start_time));
    const first = sorted[0];
    const last = sorted[sorted.length - 1];

    if (cell.end_time === first.start_time) {
      // Extending backward
      this._addSlotToSelection(cell);
    } else if (cell.start_time === last.end_time) {
      // Extending forward
      this._addSlotToSelection(cell);
    } else {
      // Replace selection with new slot
      this._updateSelection([this._cellToSlot(cell)]);
    }
  },

  _cellToSlot(cell) {
    const venue = this.data.displayVenues[0];
    return {
      slot_id: cell.slot_id,
      venue_id: cell.venue_id,
      venue_name: (venue || {}).name || '',
      price: cell.price,
      start_time: cell.start_time,
      end_time: cell.end_time,
      date: this.data.selectedDate,
    };
  },

  _addSlotToSelection(cell) {
    const slot = this._cellToSlot(cell);
    const newSelected = [...this.data.selectedSlots, slot]
      .sort((a, b) => a.start_time.localeCompare(b.start_time));
    this._updateSelection(newSelected);
  },

  _updateSelection(selectedSlots) {
    const sorted = selectedSlots.slice().sort((a, b) => a.start_time.localeCompare(b.start_time));
    const totalPrice = sorted.reduce((sum, s) => sum + parseFloat(s.price || 0), 0);
    const start = sorted[0] ? sorted[0].start_time : '';
    const end = sorted[sorted.length - 1] ? sorted[sorted.length - 1].end_time : '';
    this.setData({
      selectedSlots: sorted,
      totalPrice,
      selectedDuration: this._calcDuration(start, end),
      displayRows: this.markSelectedRows(this.data.displayRows, sorted),
    });
  },

  onSlotLongPress(e) {
    if (!this.data.isClubAdmin) return;
    const { rowIndex } = e.currentTarget.dataset;
    const cell = this.data.displayRows[rowIndex].cells[0];
    if (!['available', 'maintenance'].includes(cell.status)) {
      return wx.showToast({ title: '该状态不可切换', icon: 'none' });
    }
    const nextStatus = cell.status === 'available' ? 'maintenance' : 'available';
    const actionText = nextStatus === 'maintenance' ? '设为维护' : '恢复可订';
    const venue = this.data.displayVenues[0];
    wx.showModal({
      title: `${actionText} - ${(venue || {}).name || ''}`,
      content: `${cell.start_time} - ${cell.end_time}`,
      success: (res) => {
        if (res.confirm) {
          this.updateSlotStatus(cell.slot_id, cell.venue_id, nextStatus);
        }
      },
    });
  },

  async updateSlotStatus(slotId, venueId, status) {
    try {
      await app.request({
        url: `/venues/${venueId}/slots/${slotId}/status`,
        method: 'PATCH',
        data: { status },
      });
      wx.showToast({ title: '状态已更新', icon: 'success' });
      this.loadSlots(this.data.selectedDate);
    } catch (e) {
      const msg = (e.data && e.data.detail) || '更新失败';
      wx.showToast({ title: msg, icon: 'none' });
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
      displayRows: this.markSelectedRows(this.data.displayRows, []),
    });
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

  onPhoneTap() {
    const phone = (this.data.club || {}).contact_phone;
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
