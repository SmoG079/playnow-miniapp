const app = getApp();
const wxpay = require('../../utils/wxpay');

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
    venueId: null,
    price: 0,
    date: '',
    startTime: '',
    endTime: '',
    venueName: '',
    clubName: '',
    duration: '',
    booking: null,
    paying: false,
    countdownText: '',
    countdownExpired: false,
  },

  _countdownTimer: null,

  onLoad(options) {
    if (!app.requireLogin({ redirect: `/pages/booking/confirm?slot_id=${options.slot_id}&venue_id=${options.venue_id}&price=${options.price}&date=${options.date}&start=${options.start}&end=${options.end}&venue_name=${options.venue_name}&club_name=${options.club_name}` })) {
      return;
    }
    this.setData({
      slotId: options.slot_id,
      venueId: options.venue_id,
      price: parseFloat(options.price) || 0,
      date: options.date,
      startTime: options.start,
      endTime: options.end,
      venueName: options.venue_name || '',
      clubName: options.club_name || '',
      duration: this._calcDuration(options.start, options.end),
    });
    if (!this.data.venueName || !this.data.clubName) {
      this.loadVenueInfo();
    }
  },

  onShow() {
    if (!app.requireLogin({ redirect: `/pages/booking/confirm?slot_id=${this.data.slotId}&venue_id=${this.data.venueId}&price=${this.data.price}&date=${this.data.date}&start=${this.data.startTime}&end=${this.data.endTime}&venue_name=${this.data.venueName}&club_name=${this.data.clubName}` })) {
      return;
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
      const booking = await app.request({
        url: '/bookings',
        method: 'POST',
        data: { slot_id: parseInt(this.data.slotId) },
      });
      this.setData({ booking });
      this._startCountdown(booking);
      return booking;
    } catch (e) {
      wx.showToast({ title: '创建订单失败', icon: 'none' });
      throw e;
    }
  },

  async onPay() {
    if (this.data.paying || this.data.countdownExpired) return;
    this.setData({ paying: true });

    try {
      // 1. Create booking (lock slot)
      let booking = this.data.booking;
      if (!booking) {
        booking = await this.onCreateBooking();
      }

      // 2. Initiate WeChat payment
      await wxpay.payBooking(booking.id);

      // 3. Redirect to success page
      wx.redirectTo({
        url: `/pages/booking/success?booking_id=${booking.id}&order_no=${booking.order_no}`,
      });
    } catch (e) {
      if (e.message !== '用户取消支付') {
        wx.showToast({ title: '支付失败，请重试', icon: 'none' });
      }
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
