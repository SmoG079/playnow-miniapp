const app = getApp();
const perm = require('../../utils/permission');

const STATUS_TABS = [
  { label: '全部', value: '' },
  { label: '待支付', value: 'pending' },
  { label: '已支付', value: 'paid' },
  { label: '已完成', value: 'completed' },
  { label: '已取消', value: 'cancelled' },
  { label: '退款中', value: 'refunding' },
  { label: '已退款', value: 'refunded' },
];

Page({
  data: {
    clubId: null,
    statusTabs: STATUS_TABS,
    activeStatus: '',
    orders: [],
    loading: false,
    page: 1,
    pageSize: 20,
    hasMore: true,
  },

  onLoad(options) {
    if (!perm.requireClubAdmin()) return;
    const clubId = options.club_id || perm.getManagedClubIds()[0];
    if (!clubId) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      return wx.navigateBack();
    }
    this.setData({ clubId: parseInt(clubId) });
    this.loadOrders(true);
  },

  async loadOrders(reset = false) {
    if (this.data.loading) return;
    const page = reset ? 1 : this.data.page;
    this.setData({ loading: true });
    try {
      let url = `/bookings/club/${this.data.clubId}?page=${page}&page_size=${this.data.pageSize}`;
      if (this.data.activeStatus) url += `&status=${this.data.activeStatus}`;
      const res = await app.request({ url });
      const items = res.items || [];
      this.setData({
        orders: reset ? items : [...this.data.orders, ...items],
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
    this.setData({ activeStatus: status, orders: [], page: 1, hasMore: true });
    this.loadOrders(true);
  },

  onCancel(e) {
    const id = parseInt(e.currentTarget.dataset.id);
    const order = this.data.orders.find((o) => o.id === id);
    if (!order || (order.status !== 'pending' && order.status !== 'paid')) {
      return wx.showToast({ title: '该订单无法取消', icon: 'none' });
    }
    wx.showModal({
      title: '取消订单',
      content: `确定取消订单 ${order.order_no} 吗？`,
      confirmColor: '#f44336',
      success: (res) => {
        if (res.confirm) this.doCancel(order.id);
      },
    });
  },

  async doCancel(orderId) {
    try {
      await app.request({
        url: `/bookings/${orderId}/cancel`,
        method: 'POST',
        data: { reason: '管理员取消' },
      });
      wx.showToast({ title: '已取消', icon: 'success' });
      this.loadOrders(true);
    } catch (e) {
      wx.showToast({ title: '取消失败', icon: 'none' });
    }
  },

  onReachBottom() {
    if (this.data.hasMore && !this.data.loading) this.loadOrders();
  },

  onPullDownRefresh() {
    this.loadOrders(true).then(() => wx.stopPullDownRefresh());
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
