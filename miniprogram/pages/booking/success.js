Page({
  data: {
    bookingId: null,
    orderNo: '',
  },

  onLoad(options) {
    this.setData({
      bookingId: options.booking_id,
      orderNo: options.order_no || '',
    });
  },

  onViewBooking() {
    wx.switchTab({ url: '/pages/profile/index' });
  },

  onBackHome() {
    wx.switchTab({ url: '/pages/home/index' });
  },
});
