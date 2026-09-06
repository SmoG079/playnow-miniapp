const app = getApp();
const perm = require('../../utils/permission');

Page({
  data: {
    messages: [],
    loading: false,
    page: 1,
    pageSize: 20,
    hasMore: true,
    unreadCount: 0,
  },

  onLoad() {
    if (!perm.requireLogin()) return;
    this.loadMessages(true);
    this.loadUnreadCount();
  },

  onShow() {
    if (perm.isLoggedIn()) {
      this.loadMessages(true);
      this.loadUnreadCount();
    }
  },

  async loadMessages(reset = false) {
    if (this.data.loading) return;
    const page = reset ? 1 : this.data.page;
    this.setData({ loading: true });
    try {
      const res = await app.request({
        url: `/users/me/notifications?page=${page}&page_size=${this.data.pageSize}`,
      });
      const items = (res.items || []).map(item => ({ ...item, timeText: this.formatTime(item.created_at) }));
      this.setData({
        messages: reset ? items : [...this.data.messages, ...items],
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

  async loadUnreadCount() {
    try {
      const res = await app.request({ url: '/users/me/notifications/unread-count' });
      this.setData({ unreadCount: res.count || 0 });
    } catch (e) {
      console.error(e);
    }
  },

  onMessageTap(e) {
    const message = e.currentTarget.dataset.message;
    if (!message) return;
    if (!message.is_read) {
      this.markRead(message.id);
    }
    wx.navigateTo({ url: `/pages/message/detail?id=${message.id}` });
  },

  async markRead(id) {
    try {
      await app.request({
        url: `/users/me/notifications/${id}/read`,
        method: 'PUT',
      });
      const messages = this.data.messages.map(m =>
        m.id === id ? { ...m, is_read: true } : m
      );
      this.setData({ messages });
      this.loadUnreadCount();
    } catch (e) {
      console.error(e);
    }
  },

  onReachBottom() {
    if (this.data.hasMore && !this.data.loading) {
      this.loadMessages();
    }
  },

  onPullDownRefresh() {
    Promise.all([
      this.loadMessages(true),
      this.loadUnreadCount(),
    ]).then(() => wx.stopPullDownRefresh());
  },

  formatTime(time) {
    if (!time) return '';
    const date = new Date(time);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();
    const pad = n => (n < 10 ? '0' + n : n);
    if (isToday) {
      return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }
    return `${date.getMonth() + 1}-${date.getDate()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  },
});
