const app = getApp();
const auth = require('../../utils/auth');

// Must stay in sync with backend BOOKING_LOCK_TTL_SECONDS
const LOCK_TTL_SECONDS = 600;

function formatCountdown(seconds) {
  if (seconds <= 0) return '00:00';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

Page({
  data: {
    slotId: null,
    slotIds: [],
    venueId: null,
    price: 0,
    date: '',
    startTime: '',
    endTime: '',
    venueName: '',
    clubName: '',
    duration: '',
    returnMode: '',
    booking: null,
    paying: false,
    countdownText: '',
    countdownExpired: false,
  },

  _countdownTimer: null,

  onLoad(options) {
    options = options || {};
    const slotIds = options.slot_ids ? options.slot_ids.split(',').map(Number) : (options.slot_id ? [parseInt(options.slot_id)] : []);
    const redirectUrl = `/pages/booking/confirm?slot_ids=${(options.slot_ids || '')}&venue_id=${options.venue_id || ''}&price=${options.price || ''}&date=${options.date || ''}&start=${options.start || ''}&end=${options.end || ''}&venue_name=${encodeURIComponent(options.venue_name || '')}&club_name=${encodeURIComponent(options.club_name || '')}`;
    if (!app.requireLogin({ redirect: redirectUrl })) {
      return;
    }
    const clubName = options.club_name ? decodeURIComponent(options.club_name) : '';
    const venueName = options.venue_name ? decodeURIComponent(options.venue_name) : '';
    const price = parseFloat(options.price) || 0;
    this.setData({
      slotId: slotIds[0] || null,
      slotIds,
      venueId: options.venue_id,
      price,
      priceText: price.toFixed(2),
      date: options.date,
      startTime: options.start,
      endTime: options.end,
      venueName,
      clubName,
      duration: this._calcDuration(options.start, options.end),
      returnMode: options.return_mode || '',
    });
    if (!venueName || !clubName) {
      this.loadVenueInfo();
    }
  },

  onShow() {
    if (this.data.slotIds.length > 0) {
      const slotIdsStr = this.data.slotIds.join(',');
      if (!app.requireLogin({ redirect: `/pages/booking/confirm?slot_ids=${slotIdsStr}&venue_id=${this.data.venueId}&price=${this.data.price}&date=${this.data.date}&start=${this.data.startTime}&end=${this.data.endTime}&venue_name=${encodeURIComponent(this.data.venueName)}&club_name=${encodeURIComponent(this.data.clubName)}` })) {
        return;
      }
    } else {
      if (!app.requireLogin()) return;
    }
    if (this.data.booking && (this.data.booking.status === 'pending' || this.data.booking.status === 'locked')) {
      this._startCountdown(this.data.booking);
    }
  },

  onHide() {
    this._clearCountdown();
  },

  _calcDuration(start, end) {
    if (!start || !end) return '';
    const [sh, sm] = start.split(':').map(Number);
    const [eh, em] = end.split(':').map(Number);
    const minutes = (eh * 60 + em) - (sh * 60 + sm);
    if (minutes <= 0) return '';
    if (minutes >= 60) {
      const h = Math.floor(minutes / 60);
      const m = minutes % 60;
      return m > 0 ? `${h}小时${m}分钟` : `${h}小时`;
    }
    return `${minutes}分钟`;
  },

  async loadVenueInfo() {
    try {
      const venue = await app.request({ url: `/venues/${this.data.venueId}` });
      this.setData({ venueName: venue.name });
      if (venue.club_id) {
        const club = await app.request({ url: `/clubs/${venue.club_id}` });
        this.setData({ clubName: club.name });
      }
    } catch (e) {
      console.error(e);
    }
  },

  _startCountdown(booking) {
    this._clearCountdown();
    const lockedAt = booking && booking.locked_at ? new Date(booking.locked_at) : null;
    if (!lockedAt || isNaN(lockedAt.getTime())) {
      this.setData({ countdownText: '', countdownExpired: false });
      return;
    }
    const expiry = lockedAt.getTime() + LOCK_TTL_SECONDS * 1000;

    const tick = () => {
      const remaining = Math.ceil((expiry - Date.now()) / 1000);
      if (remaining <= 0) {
        this.setData({ countdownText: '锁定已过期，请重新选择场地', countdownExpired: true });
        this._clearCountdown();
        return;
      }
      this.setData({ countdownText: `支付倒计时 ${formatCountdown(remaining)}`, countdownExpired: false });
    };

    tick();
    this._countdownTimer = setInterval(tick, 1000);
  },

  _clearCountdown() {
    if (this._countdownTimer) {
      clearInterval(this._countdownTimer);
      this._countdownTimer = null;
    }
  },

  async onCreateBooking() {
    try {
      const payload = this.data.slotIds.length > 1
        ? { slot_ids: this.data.slotIds }
        : { slot_id: this.data.slotIds[0] };
      const booking = await app.request({
        url: '/bookings',
        method: 'POST',
        data: payload,
      });
      this.setData({ booking });
      this._startCountdown(booking);
      return booking;
    } catch (e) {
      const detail = (e.data && e.data.detail) || '';
      const is409 = e.statusCode === 409;
      const msg = is409 ? (detail || '该时段已被他人锁定，请重新选择') : '创建订单失败';
      wx.showToast({ title: msg, icon: 'none', duration: 2000 });
      if (is409) {
        setTimeout(() => wx.navigateBack(), 1500);
      }
      throw e;
    }
  },

  async onPay() {
    if (this.data.paying || this.data.countdownExpired) return;
    if (!auth.requirePhone()) return;
    this.setData({ paying: true });

    try {
      let booking = this.data.booking;
      if (!booking) {
        booking = await this.onCreateBooking();
      }

      // Placeholder: mark as paid directly (skip WeChat Pay)
      const payRes = await app.request({ url: `/bookings/${booking.id}/pay`, method: 'POST' });
      if (payRes.already_paid) {
        wx.showToast({ title: '已经支付过了', icon: 'none' });
      }

      wx.showToast({ title: '支付成功', icon: 'success', duration: 500 });

      const that = this;
      setTimeout(function() {
        if (that.data.returnMode === 'post' || that.data.returnMode === 'tournament') {
          const targetPage = that.data.returnMode === 'tournament' ? 'tournament-create' : 'post-create';
          const tabPages = ['post-create', 'tournament-create'];
          // Store booking info in globalData for the target page to read
          const app = getApp();
          app.globalData._bookingReturn = {
            booking_id: booking.id,
            venue_id: that.data.venueId,
            venue_name: that.data.venueName,
            slot_date: that.data.date,
            slot_start: that.data.startTime,
            slot_end: that.data.endTime,
          };
          if (tabPages.includes(targetPage)) {
            wx.switchTab({ url: `/pages/publish/${targetPage}` });
          } else {
            wx.redirectTo({
              url: `/pages/publish/${targetPage}?booking_id=${booking.id}&venue_id=${that.data.venueId}&venue_name=${encodeURIComponent(that.data.venueName)}&slot_date=${that.data.date}&slot_start=${that.data.startTime}&slot_end=${that.data.endTime}`,
            });
          }
        } else {
          wx.redirectTo({
            url: `/pages/booking/success?booking_id=${booking.id}&order_no=${booking.order_no}`,
          });
        }
      }, 500);
    } catch (e) {
      wx.showToast({ title: '支付失败，请重试', icon: 'none' });
    } finally {
      this.setData({ paying: false });
    }
  },

  onCancel() {
    wx.navigateBack();
  },

  onUnload() {
    this._clearCountdown();
  },
});
