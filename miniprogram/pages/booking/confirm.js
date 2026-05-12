const app = getApp();
const wxpay = require('../../utils/wxpay');

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
    booking: null,
    paying: false,
  },

  onLoad(options) {
    this.setData({
      slotId: options.slot_id,
      venueId: options.venue_id,
      price: parseFloat(options.price) || 0,
      date: options.date,
      startTime: options.start,
      endTime: options.end,
    });
    this.loadVenueInfo();
  },

  async loadVenueInfo() {
    try {
      const venue = await app.request({ url: `/venues/${this.data.venueId}` });
      this.setData({ venueName: venue.name });
    } catch (e) {
      console.error(e);
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
      return booking;
    } catch (e) {
      wx.showToast({ title: '创建订单失败', icon: 'none' });
      throw e;
    }
  },

  async onPay() {
    if (this.data.paying) return;
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
});
