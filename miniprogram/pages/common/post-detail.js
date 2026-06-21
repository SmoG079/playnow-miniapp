const app = getApp();

Page({
  data: {
    postId: null,
    post: null,
    loading: false,
    showRegisterInput: false,
    registerMessage: '',
    isOwner: false,
    statusLabel: { pending: '待审核', approved: '已通过', rejected: '已拒绝' },
  },

  onLoad(options) {
    this.setData({ postId: options.id });
    this.loadPost();
  },

  async loadPost() {
    this.setData({ loading: true });
    try {
      const post = await app.request({ url: `/posts/${this.data.postId}` });
      const userId = app.globalData.userInfo?.id;
      this.setData({
        post,
        isOwner: userId === post.user_id,
      });
    } catch (e) {
      console.error('Load post failed', e);
    } finally {
      this.setData({ loading: false });
    }
  },

  onRegister() {
    this.setData({ showRegisterInput: true, registerMessage: '' });
  },

  onMessageInput(e) {
    this.setData({ registerMessage: e.detail.value });
  },

  onCancelRegister() {
    this.setData({ showRegisterInput: false });
  },

  async onConfirmRegister() {
    try {
      await app.request({
        url: `/posts/${this.data.postId}/register`,
        method: 'POST',
        data: { message: this.data.registerMessage || '' },
      });
      wx.showToast({ title: '报名成功', icon: 'success' });
      this.setData({ showRegisterInput: false });
      this.loadPost();
    } catch (e) {
      if (e.data?.statusCode === 409) {
        wx.showToast({ title: '已报名，不可重复', icon: 'none' });
      }
    }
  },

  async onCancelMyRegistration() {
    wx.showModal({
      title: '确认取消',
      content: '确定取消报名吗？',
      success: async (res) => {
        if (!res.confirm) return;
        try {
          await app.request({
            url: `/posts/${this.data.postId}/register`,
            method: 'DELETE',
          });
          wx.showToast({ title: '已取消', icon: 'success' });
          this.loadPost();
        } catch (e) { console.error(e); }
      },
    });
  },

  onReview(e) {
    // P1: review will be implemented later
    wx.showToast({ title: '审核功能即将上线', icon: 'none' });
  },

  onShareAppMessage() {
    return {
      title: this.data.post?.title || '约球帖',
      path: `/pages/common/post-detail?id=${this.data.postId}`,
    };
  },

  onViewUser(e) {
    const userId = e.currentTarget.dataset.uid;
    wx.navigateTo({ url: `/pages/common/user-profile?id=${userId}` });
  },
});
