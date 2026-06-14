const app = getApp();
const perm = require('../../utils/permission');

Page({
  data: {
    clubId: null,
    venues: [],
    venueIndex: 0,
    dateFrom: '',
    dateTo: '',
    startTime: '08:00',
    endTime: '22:00',
    intervalIndex: 1, // 60 min default
    intervals: [30, 60, 90, 120],
    intervalLabels: ['30分钟', '60分钟', '90分钟', '120分钟'],
    priceRules: [],
    generating: false,
    result: null,

    slots: [],
    slotsLoading: false,
  },

  onLoad(options) {
    if (!perm.requireClubAdmin()) return;
    const clubId = options.club_id || perm.getManagedClubIds()[0];
    if (!clubId) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      return wx.navigateBack();
    }
    this.setData({ clubId: parseInt(clubId) });

    // Pre-select venue if passed
    if (options.venue_id) {
      this.setData({ preselectVenueId: parseInt(options.venue_id) });
    }

    // Set default dates (today to +7 days)
    const today = new Date();
    const nextWeek = new Date(today);
    nextWeek.setDate(today.getDate() + 7);
    this.setData({
      dateFrom: this._fmtDate(today),
      dateTo: this._fmtDate(nextWeek),
    });

    this.loadVenues();
  },

  _fmtDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  },

  async loadVenues() {
    try {
      const res = await app.request({ url: `/clubs/${this.data.clubId}/venues` });
      const venues = res || [];
      let venueIndex = 0;
      if (this.data.preselectVenueId) {
        const idx = venues.findIndex(v => v.id === this.data.preselectVenueId);
        if (idx >= 0) venueIndex = idx;
      }
      this.setData({ venues, venueIndex });
      if (venues.length > 0) {
        this.loadSlots();
      }
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '加载场地失败', icon: 'none' });
    }
  },

  async loadSlots() {
    if (this.data.venues.length === 0) return;
    const venue = this.data.venues[this.data.venueIndex];
    this.setData({ slotsLoading: true });
    try {
      const res = await app.request({
        url: `/venues/${venue.id}/slots?date_from=${this.data.dateFrom}&date_to=${this.data.dateTo}`,
      });
      const slots = [];
      (res || []).forEach(group => {
        (group.slots || []).forEach(s => {
          slots.push({ ...s, date_label: group.date });
        });
      });
      this.setData({ slots });
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '加载时段失败', icon: 'none' });
    } finally {
      this.setData({ slotsLoading: false });
    }
  },

  async onToggleSlotStatus(e) {
    const { slotId, status } = e.currentTarget.dataset;
    const venue = this.data.venues[this.data.venueIndex];
    const nextStatus = status === 'available' ? 'maintenance' : 'available';
    try {
      await app.request({
        url: `/venues/${venue.id}/slots/${slotId}/status`,
        method: 'PATCH',
        data: { status: nextStatus },
      });
      wx.showToast({ title: '状态已更新', icon: 'success' });
      this.loadSlots();
    } catch (e) {
      const msg = (e.data && e.data.detail) || '更新失败';
      wx.showToast({ title: msg, icon: 'none' });
    }
  },

  onVenueChange(e) {
    this.setData({ venueIndex: parseInt(e.detail.value) }, () => this.loadSlots());
  },

  onDateFromChange(e) {
    this.setData({ dateFrom: e.detail.value }, () => this.loadSlots());
  },

  onDateToChange(e) {
    this.setData({ dateTo: e.detail.value }, () => this.loadSlots());
  },

  onStartTimeChange(e) {
    this.setData({ startTime: e.detail.value });
  },

  onEndTimeChange(e) {
    this.setData({ endTime: e.detail.value });
  },

  onIntervalChange(e) {
    this.setData({ intervalIndex: parseInt(e.detail.value) });
  },

  onAddPriceRule() {
    const rules = this.data.priceRules.concat([{ start_time: '08:00', end_time: '12:00', price: '' }]);
    this.setData({ priceRules: rules });
  },

  onRemovePriceRule(e) {
    const idx = e.currentTarget.dataset.index;
    const rules = this.data.priceRules.filter((_, i) => i !== idx);
    this.setData({ priceRules: rules });
  },

  onRuleFieldChange(e) {
    const { index, field } = e.currentTarget.dataset;
    const value = e.detail.value;
    const rules = this.data.priceRules.map((r, i) => i === index ? { ...r, [field]: value } : r);
    this.setData({ priceRules: rules });
  },

  async onGenerate() {
    const { venues, venueIndex, dateFrom, dateTo, startTime, endTime, intervals, intervalIndex, priceRules } = this.data;
    if (venues.length === 0) {
      return wx.showToast({ title: '没有可用场地', icon: 'none' });
    }
    if (dateTo < dateFrom) {
      return wx.showToast({ title: '结束日期不能早于开始日期', icon: 'none' });
    }
    const dayDiff = (new Date(dateTo) - new Date(dateFrom)) / (1000 * 60 * 60 * 24);
    if (dayDiff > 31) {
      return wx.showToast({ title: '最多生成31天的时段', icon: 'none' });
    }
    if (endTime <= startTime) {
      return wx.showToast({ title: '结束时间必须晚于开始时间', icon: 'none' });
    }

    const venue = venues[venueIndex];
    this.setData({ generating: true, result: null });

    try {
      const rules = priceRules
        .filter(r => {
          const price = parseFloat(r.price);
          return !isNaN(price) && price > 0;
        })
        .map(r => ({
          start_time: r.start_time,
          end_time: r.end_time,
          price: parseFloat(r.price),
        }));
      const res = await app.request({
        url: `/venues/${venue.id}/slots/batch`,
        method: 'POST',
        data: {
          date_from: dateFrom,
          date_to: dateTo,
          start_time: startTime,
          end_time: endTime,
          interval_minutes: intervals[intervalIndex],
          price_rules: rules,
        },
      });
      this.setData({ result: res });
      wx.showToast({ title: `新增${res.created}个时段`, icon: 'success' });
      this.loadSlots();
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '生成失败', icon: 'none' });
    } finally {
      this.setData({ generating: false });
    }
  },
});
