const app = getApp();

const minutes = time => {
  const parts = String(time || '').split(':').map(Number);
  return parts[0] * 60 + parts[1];
};
const duration = slots => slots.reduce((sum, s) => sum + minutes(s.end_time) - minutes(s.start_time), 0);

Page({
  data: {
    clubId: null,
    club: null,
    venues: [],
    selectedDate: '',
    dateOptions: [],
    grid: [],
    selectedSlots: [],
    totalPrice: 0,
    selectedInfo: null,
    loading: false,
    statusBarH: 0,
    showDesc: false,
    showRules: false,
  },

  onToggleDesc() { this.setData({ showDesc: !this.data.showDesc }); },
  onToggleRules() { this.setData({ showRules: !this.data.showRules }); },

  onLoad(options) {
    const barH = wx.getSystemInfoSync().statusBarHeight || 20;
    this.setData({ clubId: options.id || options.club_id, statusBarH: barH, returnMode: options.return_mode || '' });
    this.initDates();
    this.loadClub();
  },

  onBack() { wx.navigateBack(); },

  initDates() {
    const dates = [];
    const today = new Date();
    for (let i = 0; i < 3; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() + i);
      dates.push({
        value: this.formatDate(d),
        label: i === 0 ? '今天' : i === 1 ? '明天' : `${d.getMonth()+1}/${d.getDate()}`,
      });
    }
    this.setData({ dateOptions: dates, selectedDate: dates[0].value });
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
      if (!club.images || !club.images.length) {
        club.images = club.cover_image ? [club.cover_image] : [];
      }
      const venues = club.venues || [];
      this.setData({ club, venues });
      if (venues.length > 0) {
        this.loadSlots(this.data.selectedDate);
      }
    } catch (e) {
      console.error('Load club failed', e);
    }
  },

  _nowStr() {
    const n = new Date();
    return `${String(n.getHours()).padStart(2,'0')}:${String(n.getMinutes()).padStart(2,'0')}`;
  },

  async loadSlots(date) {
    const requestId = this._slotRequestId = (this._slotRequestId || 0) + 1;
    this.setData({ loading: true, selectedSlots: [], totalPrice: 0, selectedInfo: null });
    try {
      const res = await app.request({ url: `/clubs/${this.data.clubId}/venue-slots?date=${date}` });
      if (requestId !== this._slotRequestId) return;
      const venues = res.venues || [];
      const rows = res.rows || [];
      this.setData({ venues });

      const slotMaps = {};
      for (const row of rows) {
        for (const cell of row.cells) {
          const vkey = `${cell.venue_id}`;
          if (!slotMaps[vkey]) slotMaps[vkey] = {};
          slotMaps[vkey][row.time_label] = cell;
        }
      }

      const now = this._nowStr();
      const grid = rows.map(row => row.time_label).sort().map(tl => ({
        time_label: tl,
        cells: venues.map(venue => {
          const slot = slotMaps[venue.id]?.[tl];
          const past = date < this.data.dateOptions[0].value || (date === this.data.dateOptions[0].value && tl < now);
          return {
            venue_id: venue.id,
            date,
            slot_id: slot?.slot_id,
            start_time: slot?.start_time || tl,
            end_time: slot?.end_time,
            price: slot?.price,
            status: past ? 'past' : (slot?.slot_id ? slot.status : 'none'),
            _sel: false,
          };
        }),
      }));

      this.setData({ grid });
    } catch (e) {
      console.error('Load slots failed', e);
    } finally {
      if (requestId === this._slotRequestId) this.setData({ loading: false });
    }
  },

  onDateChange(e) {
    const date = e.currentTarget.dataset.date;
    this.setData({ selectedDate: date, selectedSlots: [], totalPrice: 0, selectedInfo: null });
    this.loadSlots(date);
  },

  onSlotTap(e) {
    const { rowIdx, colIdx } = e.currentTarget.dataset;
    const cell = this.data.grid[rowIdx].cells[colIdx];
    if (cell.status !== 'available') return;

    const grid = this.data.grid;
    const sel = [...this.data.selectedSlots];

    const existIdx = sel.findIndex(s => s.slot_id === cell.slot_id);
    if (existIdx >= 0) {
      const removed = sel.splice(existIdx);
      for (const s of removed) {
        if (grid[s.row_idx]) grid[s.row_idx].cells[s.col_idx]._sel = false;
      }
      this._recalc(grid, sel);
      return;
    }

    if (sel.length === 0) {
      sel.push({ ...cell, row_idx: rowIdx, col_idx: colIdx });
      grid[rowIdx].cells[colIdx]._sel = true;
      while (duration(sel) < 60) {
        const last = sel[sel.length - 1];
        const nextRow = grid.findIndex(row => {
          const next = row.cells[colIdx];
          return next.status === 'available' && !next._sel && minutes(next.start_time) === minutes(last.end_time) && minutes(next.end_time) > minutes(next.start_time);
        });
        if (nextRow < 0) break;
        const next = grid[nextRow].cells[colIdx];
        sel.push({ ...next, row_idx: nextRow, col_idx: colIdx });
        next._sel = true;
      }
      this._recalc(grid, sel);
      return;
    }

    const lastSel = sel[sel.length - 1];
    if (lastSel.col_idx !== colIdx) {
      wx.showToast({ title: '请在同一列中选择连续时段', icon: 'none' });
      return;
    }
    if (minutes(cell.start_time) === minutes(lastSel.end_time)) {
      sel.push({ ...cell, row_idx: rowIdx, col_idx: colIdx });
      grid[rowIdx].cells[colIdx]._sel = true;
      this._recalc(grid, sel);
    } else {
      wx.showToast({ title: '请选择相邻的连续时段', icon: 'none' });
    }
  },

  _recalc(grid, sel) {
    let total = 0;
    for (const s of sel) total += parseFloat(s.price || 0);
    const first = sel[0], last = sel[sel.length - 1];
    this.setData({
      grid,
      selectedSlots: sel,
      totalPrice: total.toFixed(2),
      selectedInfo: duration(sel) >= 60 ? {
        date: first.date || this.data.selectedDate,
        start: first.start_time, end: last.end_time,
        venueId: first.venue_id,
      } : null,
    });
  },

  onBook() {
    const sel = this.data.selectedSlots;
    const info = this.data.selectedInfo;
    if (duration(sel) < 60 || !info) {
      wx.showToast({ title: '请至少选择 1 小时', icon: 'none' });
      return;
    }
    const venue = this.data.venues.find(v => v.id === info.venueId) || {};
    const returnParam = this.data.returnMode ? `&return_mode=${this.data.returnMode}` : '';
    wx.navigateTo({
      url: `/pages/booking/confirm?slot_ids=${sel.map(s => s.slot_id).join(',')}&venue_id=${info.venueId}&price=${this.data.totalPrice}&date=${info.date}&start=${info.start}&end=${info.end}&venue_name=${encodeURIComponent(venue.name || '')}${returnParam}`,
    });
  },
});
