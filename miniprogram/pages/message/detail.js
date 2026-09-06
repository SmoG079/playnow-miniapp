const app = getApp();
const perm = require('../../utils/permission');

Page({
  data: {
    messageId: null,
    message: null,
    loading: false,
  },

  onLoad(options) {
    if (!perm.requireLogin()) return;
    const id = options.id;
    if (!id) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      return wx.navigateBack();
    }
    this.setData({ messageId: id });
    this.loadMessage();
  },

  async loadMessage() {
    this.setData({ loading: true });
    try {
      const message = await app.request({ url: `/users/me/notifications/${this.data.messageId}` });
      this.setData({ message, loading: false, timeText: this.formatTime(message.created_at) });
      if (!message.is_read) {
        this.markRead(this.data.messageId);
      }
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  async markRead(id) {
    try {
      await app.request({
        url: `/users/me/notifications/${id}/read`,
        method: 'PUT',
      });
    } catch (e) {
      console.error(e);
    }
  },

  formatTime(time) {
    if (!time) return '';
    const date = new Date(time);
    const pad = n => (n < 10 ? '0' + n : n);
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  },
});
