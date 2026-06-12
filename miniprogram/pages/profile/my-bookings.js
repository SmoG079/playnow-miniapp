const app = getApp();
const perm = require('../../utils/permission');

const STATUS_TABS = [
  { label: '全部', value: '' },
  { label: '待支付', value: 'pending' },
  { label: '已支付', value: 'paid' },
  { label: '已完成', value: 'completed' },
  { label: '已取消', value: 'cancelled' },
];

Page({
  data: {
    statusTabs: STATUS_TABS,
    activeStatus: '',
    bookings: [],
    loading: false,
    page: 1,
    pageSize: 20,
    hasMore: true,
  },

  onShow() {
    if (!perm.requireLogin()) return;
    this.loadBookings(true);
  },

  async loadBookings(reset = false) {
    if (this.data.loading) return;
    const page = reset ? 1 : this.data.page;
    this.setData({ loading: true });

    try {
      let url = `/users/me/bookings?page=${page}&page_size=${this.data.pageSize}`;
      if (this.data.activeStatus) {
        url += `&status=${this.data.activeStatus}`;
      }
      const res = await app.request({ url });
      const items = res.items || [];
      this.setData({
        bookings: reset ? items : [...this.data.bookings, ...items],
        page: page + 1,
        hasMore: items.length === this.data.pageSize,
        loading: false,
      });
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  onTabChange(e) {
    const status = e.currentTarget.dataset.status;
    this.setData({ activeStatus: status, bookings: [], page: 1, hasMore: true });
    this.loadBookings(true);
  },

  onCancelBooking(e) {
    const booking = e.currentTarget.dataset.booking;
    if (!booking || booking.status !== 'pending') {
      return wx.showToast({ title: '该订单无法取消', icon: 'none' });
    }
    wx.showModal({
      title: '取消预约',
      content: `确定要取消订单 ${booking.order_no} 吗？`,
      confirmColor: '#f44336',
      success: (res) => {
        if (res.confirm) this.doCancel(booking.id);
      },
    });
  },

  async doCancel(bookingId) {
    try {
      await app.request({
        url: `/bookings/${bookingId}/cancel`,
        method: 'POST',
        data: { reason: '用户取消' },
      });
      wx.showToast({ title: '已取消', icon: 'success' });
      this.loadBookings(true);
    } catch (e) {
      wx.showToast({ title: '取消失败', icon: 'none' });
    }
  },

  onReachBottom() {
    if (this.data.hasMore && !this.data.loading) {
      this.loadBookings();
    }
  },

  onPullDownRefresh() {
    this.loadBookings(true).then(() => wx.stopPullDownRefresh());
  },

  formatStatus(status) {
    const map = {
      pending: '待支付',
      paid: '已支付',
      completed: '已完成',
      cancelled: '已取消',
      refunding: '退款中',
      refunded: '已退款',
    };
    return map[status] || status;
  },

  statusColor(status) {
    const map = {
      pending: 'orange',
      paid: 'green',
      completed: 'blue',
      cancelled: 'gray',
      refunding: 'red',
      refunded: 'gray',
    };
    return map[status] || 'gray';
  },
});
