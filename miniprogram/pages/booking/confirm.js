const app = getApp();

Page({
  data: {
    slotId: null,
    slot2Id: null,
    venueId: null,
    price: 0,
    date: '',
    startTime: '',
    endTime: '',
    venueName: '',
    booking: null,
    paying: false,
  },

  onLoad(options) {
    this.setData({
      slotId: options.slot_id,
      slot2Id: options.slot2_id || null,
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
    } catch (e) { console.error(e); }
  },

  async onCreateBooking() {
    try {
      const data = { slot_id: parseInt(this.data.slotId) };
      if (this.data.slot2Id) data.slot2_id = parseInt(this.data.slot2Id);
      const booking = await app.request({
        url: '/bookings', method: 'POST', data,
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
      let booking = this.data.booking;
      if (!booking) booking = await this.onCreateBooking();
      // Placeholder: pay endpoint marks order as paid directly
      await app.request({ url: `/bookings/${booking.id}/pay`, method: 'POST' });
      wx.redirectTo({
        url: `/pages/booking/success?booking_id=${booking.id}&order_no=${booking.order_no}`,
      });
    } catch (e) {
      wx.showToast({ title: '支付失败，请重试', icon: 'none' });
    } finally {
      this.setData({ paying: false });
    }
  },

  onCancel() { wx.navigateBack(); },
});
