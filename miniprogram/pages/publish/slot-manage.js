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
    generating: false,
    result: null,
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
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '加载场地失败', icon: 'none' });
    }
  },

  onVenueChange(e) {
    this.setData({ venueIndex: parseInt(e.detail.value) });
  },

  onDateFromChange(e) {
    this.setData({ dateFrom: e.detail.value });
  },

  onDateToChange(e) {
    this.setData({ dateTo: e.detail.value });
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

  async onGenerate() {
    const { venues, venueIndex, dateFrom, dateTo, startTime, endTime, intervals, intervalIndex } = this.data;
    if (venues.length === 0) {
      return wx.showToast({ title: '没有可用场地', icon: 'none' });
    }
    if (dateTo < dateFrom) {
      return wx.showToast({ title: '结束日期不能早于开始日期', icon: 'none' });
    }
    if (endTime <= startTime) {
      return wx.showToast({ title: '结束时间必须晚于开始时间', icon: 'none' });
    }

    const venue = venues[venueIndex];
    this.setData({ generating: true, result: null });

    try {
      const res = await app.request({
        url: `/venues/${venue.id}/slots/batch`,
        method: 'POST',
        data: {
          date_from: dateFrom,
          date_to: dateTo,
          start_time: startTime,
          end_time: endTime,
          interval_minutes: intervals[intervalIndex],
        },
      });
      this.setData({ result: res });
      wx.showToast({ title: `新增${res.created}个时段`, icon: 'success' });
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '生成失败', icon: 'none' });
    } finally {
      this.setData({ generating: false });
    }
  },
});
