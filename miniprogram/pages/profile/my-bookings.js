const app = getApp();

Page({
  data: {
    bookings: [],
    loading: false,
    activeStatus: '',
    statusFilters: [
      { label: '全部', value: '' },
      { label: '待支付', value: 'pending' },
      { label: '已支付', value: 'paid' },
      { label: '已完成', value: 'completed' },
      { label: '已取消', value: 'cancelled' },
    ],
    statusLabel: {
      pending: '待支付',
      paid: '已支付',
      cancelled: '已取消',
      refunding: '退款中',
      refunded: '已退款',
      completed: '已完成',
    },
  },

  onShow() {
    this.loadBookings();
  },

  async loadBookings() {
    this.setData({ loading: true });
    try {
      let url = '/users/me/bookings?page=1&page_size=20';
      if (this.data.activeStatus) {
        url += `&status=${this.data.activeStatus}`;
      }
      const res = await app.request({ url });
      this.setData({ bookings: res.items || [] });
    } catch (e) {
      console.error('Load bookings failed', e);
    } finally {
      this.setData({ loading: false });
    }
  },

  onStatusFilter(e) {
    const val = e.currentTarget.dataset.value;
    this.setData({ activeStatus: val });
    this.loadBookings();
  },

  async onCancelBooking(e) {
    const booking = e.currentTarget.dataset.booking;
    wx.showModal({
      title: '确认取消',
      content: `确定取消 ${booking.slot_date} ${booking.slot_start}-${booking.slot_end} 的预约吗？`,
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await app.request({
            url: `/bookings/${booking.id}/cancel`,
            method: 'POST',
            data: { reason: '用户主动取消' },
          });
          wx.showToast({ title: '已取消', icon: 'success' });
          this.loadBookings();
        } catch (e) {
          console.error('Cancel failed', e);
        }
      },
    });
  },

  onBookingDetail(e) {
    const booking = e.currentTarget.dataset.booking;
    wx.showModal({
      title: '订单详情',
      content: `订单号：${booking.order_no}\n场地：${booking.venue_name}\n日期：${booking.slot_date}\n时间：${booking.slot_start} - ${booking.slot_end}\n金额：¥${booking.amount}\n状态：${this.data.statusLabel[booking.status] || booking.status}`,
      showCancel: false,
      confirmText: '知道了',
    });
  },
});
