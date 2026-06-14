const app = getApp();

const POLL_INTERVAL = 3000;
const MAX_POLL_COUNT = 20;

Page({
  data: {
    bookingId: null,
    orderNo: '',
    booking: null,
    loading: true,
    error: false,
    pollCount: 0,
    polling: false,
  },

  onLoad(options) {
    if (!app.requireLogin()) return;
    const bookingId = options.booking_id;
    const orderNo = options.order_no;
    if (!bookingId) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      return wx.redirectTo({ url: '/pages/home/index' });
    }
    this.setData({ bookingId: parseInt(bookingId), orderNo, error: false });
    this.loadBooking();
  },

  onShow() {
    if (this.data.booking && this.data.booking.status === 'pending') {
      this.setData({ polling: true });
      this._startPolling();
    }
  },

  onHide() {
    this._stopPolling();
  },

  onUnload() {
    this._stopPolling();
  },

  async loadBooking() {
    this.setData({ loading: true, error: false });
    try {
      const booking = await app.request({
        url: `/bookings/${this.data.bookingId}`,
      });
      this.setData({ booking, loading: false });

      if (booking.status === 'pending') {
        this.setData({ polling: true });
        this._startPolling();
      }
    } catch (e) {
      this.setData({ loading: false, error: true });
      wx.showToast({ title: '加载订单失败', icon: 'none' });
    }
  },

  _startPolling() {
    if (this._pollTimer) clearTimeout(this._pollTimer);
    const poll = async () => {
      if (this.data.pollCount >= MAX_POLL_COUNT) {
        this.setData({ polling: false });
        return;
      }
      try {
        const booking = await app.request({
          url: `/bookings/${this.data.bookingId}`,
        });
        this.setData({
          booking,
          pollCount: this.data.pollCount + 1,
        });
        if (booking.status !== 'pending') {
          this.setData({ polling: false });
          return;
        }
      } catch (e) {
        console.error('Poll booking failed', e);
      }
      this._pollTimer = setTimeout(poll, POLL_INTERVAL);
    };
    this._pollTimer = setTimeout(poll, POLL_INTERVAL);
  },

  _stopPolling() {
    if (this._pollTimer) {
      clearTimeout(this._pollTimer);
      this._pollTimer = null;
    }
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

  getStatusMeta(status, polling) {
    const meta = {
      paid: { icon: 'icon-success', title: '支付成功', subtitle: '' },
      completed: { icon: 'icon-success', title: '订单已完成', subtitle: '' },
      cancelled: { icon: 'icon-warning', title: '订单已取消', subtitle: '' },
      refunding: { icon: 'icon-loading', title: '退款处理中', subtitle: '' },
      refunded: { icon: 'icon-info', title: '退款成功', subtitle: '' },
    };
    if (status === 'pending') {
      if (polling) {
        return { icon: 'icon-loading', title: '支付处理中...', subtitle: '正在确认支付结果，请稍候' };
      }
      return { icon: 'icon-info', title: '等待支付', subtitle: '' };
    }
    return meta[status] || { icon: 'icon-error', title: '支付失败', subtitle: '' };
  },

  onViewBookings() {
    wx.redirectTo({ url: '/pages/profile/my-bookings' });
  },

  onGoHome() {
    wx.switchTab({ url: '/pages/home/index' });
  },
});
