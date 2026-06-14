const app = getApp();
const perm = require('../../utils/permission');
const wxpay = require('../../utils/wxpay');

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
    freeCancelHours: 24,
  },

  onShow() {
    if (!perm.requireLogin()) return;
    this.loadConfig();
    this.loadBookings(true);
  },

  async loadConfig() {
    try {
      const res = await app.request({ url: '/bookings/config' });
      if (res && typeof res.free_cancel_hours === 'number') {
        this.setData({ freeCancelHours: res.free_cancel_hours });
      }
    } catch (e) {
      console.error('loadConfig failed', e);
    }
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

  _getBookingById(id) {
    return this.data.bookings.find((b) => b.id === id);
  },

  _showBookingExpiredAndReload() {
    wx.showToast({ title: '订单信息已过期，请刷新', icon: 'none' });
    this.loadBookings(true);
  },

  onCancelBooking(e) {
    const id = e.currentTarget.dataset.id;
    const booking = this._getBookingById(id);
    if (!booking) {
      return this._showBookingExpiredAndReload();
    }
    if (booking.status !== 'pending' && booking.status !== 'paid') {
      return wx.showToast({ title: '该订单无法取消', icon: 'none' });
    }
    if (booking.status === 'paid') {
      return this.onCancelOrRefund(e);
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

  async onPayNow(e) {
    const id = e.currentTarget.dataset.id;
    const booking = this._getBookingById(id);
    if (!booking) {
      return this._showBookingExpiredAndReload();
    }
    if (booking.status !== 'pending') {
      return wx.showToast({ title: '该订单无法支付', icon: 'none' });
    }
    try {
      await wxpay.payBooking(booking.id);
      wx.redirectTo({
        url: `/pages/booking/success?booking_id=${booking.id}&order_no=${booking.order_no}`,
      });
    } catch (e) {
      if (e.message !== '用户取消支付') {
        wx.showToast({ title: '支付失败', icon: 'none' });
      }
    }
  },

  onCancelOrRefund(e) {
    const id = e.currentTarget.dataset.id;
    const booking = this._getBookingById(id);
    if (!booking) {
      return this._showBookingExpiredAndReload();
    }
    if (booking.status !== 'paid') return;

    // Estimate refund rate based on backend FREE_CANCEL_HOURS
    const freeCancelHours = this.data.freeCancelHours;
    const now = new Date();
    const slotDate = new Date(booking.slot_date + 'T00:00:00');
    const [sh, sm] = booking.slot_start.split(':').map(Number);
    slotDate.setHours(sh, sm, 0, 0);
    const hoursBefore = (slotDate - now) / (1000 * 60 * 60);

    let refundRate = 0;
    if (hoursBefore >= freeCancelHours) refundRate = 1;
    else if (hoursBefore >= 0) refundRate = 0.5;

    if (refundRate === 0) {
      return wx.showModal({
        title: '无法退款',
        content: '已过开场时间，无法取消订单',
        showCancel: false,
      });
    }

    const refundAmount = (booking.amount * refundRate).toFixed(2);
    const refundText = refundRate === 1
      ? `开场前${freeCancelHours}小时以上取消，可全额退款`
      : `开场前${freeCancelHours}小时内取消，将退款50%`;

    wx.showModal({
      title: '取消并退款',
      content: `确定取消订单 ${booking.order_no} 吗？\n\n${refundText}\n预计退款金额：¥${refundAmount}`,
      confirmColor: '#f44336',
      success: (res) => {
        if (res.confirm) this.doCancel(booking.id);
      },
    });
  },

  async doCancel(bookingId) {
    try {
      const res = await app.request({
        url: `/bookings/${bookingId}/cancel`,
        method: 'POST',
        data: { reason: '用户取消' },
      });
      const msg = res.refund_amount ? `已发起退款 ¥${res.refund_amount}` : '已取消';
      wx.showToast({ title: msg, icon: 'success' });
      this.loadBookings(true);
    } catch (e) {
      const detail = (e.data && e.data.detail) || '取消失败';
      wx.showToast({ title: detail, icon: 'none' });
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
