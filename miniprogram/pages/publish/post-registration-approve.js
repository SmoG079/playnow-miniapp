const app = getApp();

Page({
  data: {
    postId: null,
    post: null,
    registrations: [],
    filteredRegistrations: [],
    loading: true,
    activeTab: 'pending', // pending | approved | rejected
  },

  onLoad(options) {
    const postId = options.postId;
    if (!postId) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      return wx.navigateBack();
    }
    this.setData({ postId });
    this.loadPost();
  },

  async loadPost() {
    this.setData({ loading: true });
    try {
      const post = await app.request({ url: `/posts/${this.data.postId}` });
      const registrations = post.registrations || [];
      this.setData({
        post,
        registrations,
        filteredRegistrations: this._filterRegistrations(registrations, this.data.activeTab),
        loading: false,
      });
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  _filterRegistrations(registrations, tab) {
    return registrations.filter(r => r.status === tab);
  },

  onTabChange(e) {
    const tab = e.currentTarget.dataset.tab;
    this.setData({
      activeTab: tab,
      filteredRegistrations: this._filterRegistrations(this.data.registrations, tab),
    });
  },

  async onReview(e) {
    const { userId, status } = e.currentTarget.dataset;
    try {
      await app.request({
        url: `/posts/${this.data.postId}/registrations/${userId}`,
        method: 'PUT',
        data: { status },
      });
      wx.showToast({ title: status === 'approved' ? '已通过' : '已拒绝', icon: 'success' });
      this.loadPost();
    } catch (e) {
      wx.showToast({ title: '操作失败', icon: 'none' });
    }
  },

  onPullDownRefresh() {
    this.loadPost().then(() => wx.stopPullDownRefresh());
  },
});
