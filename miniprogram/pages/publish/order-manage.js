const app = getApp();

Page({
  data: {
    clubId: null,
    orders: [],
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
      pending: '待支付', paid: '已支付', cancelled: '已取消',
      refunding: '退款中', refunded: '已退款', completed: '已完成',
    },
  },

  onShow() {
    const clubIds = app.globalData.managedClubIds || [];
    if (clubIds.length === 0) {
      wx.showToast({ title: '暂无管理权限', icon: 'none' });
      return;
    }
    this.setData({ clubId: clubIds[0] });
    this.loadOrders();
  },

  async loadOrders() {
    this.setData({ loading: true });
    try {
      let url = `/bookings/club/${this.data.clubId}?page=1&page_size=20`;
      if (this.data.activeStatus) {
        url += `&status=${this.data.activeStatus}`;
      }
      const res = await app.request({ url });
      this.setData({ orders: res.items || [] });
    } catch (e) {
      console.error('Load orders failed', e);
    } finally {
      this.setData({ loading: false });
    }
  },

  onStatusFilter(e) {
    const val = e.currentTarget.dataset.value;
    this.setData({ activeStatus: val });
    this.loadOrders();
  },

  onOrderDetail(e) {
    const order = e.currentTarget.dataset.order;
    wx.showModal({
      title: '订单详情',
      content: `订单号：${order.order_no}\n场地：${order.venue_name}\n日期：${order.slot_date}\n时间：${order.slot_start} - ${order.slot_end}\n金额：¥${order.amount}\n状态：${this.data.statusLabel[order.status]}`,
      showCancel: false,
      confirmText: '知道了',
    });
  },
});
