const app = getApp();

Page({
  data: {
    post: null,
    loading: true,
    isRegistered: false,
    isFull: false,
    isOwner: false,
    registrations: [],
    showRegPopup: false,
  },

  onLoad(options) {
    const id = options.id;
    if (!id) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      return wx.navigateBack();
    }
    this.setData({ postId: id });
    this.loadPost(id);
  },

  onBack() {
    wx.navigateBack();
  },

  async loadPost(id) {
    this.setData({ loading: true });
    try {
      const post = await app.request({ url: `/posts/${id}` });
      const currentUserId = app.globalData.userInfo && app.globalData.userInfo.id;
      const isOwner = post.user_id === currentUserId;
      const isRegistered = post.registrations && post.registrations.some(r => r.user_id === currentUserId && r.status === 'approved');
      const isFull = post.registration_count >= post.players_needed;

      this.setData({
        post,
        isOwner,
        isRegistered,
        isFull,
        registrations: post.registrations || [],
        loading: false,
      });
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  onRegister() {
    if (this.data.isOwner) {
      // 管理报名 - 跳转到管理页面
      wx.navigateTo({
        url: `/pages/publish/order-manage?postId=${this.data.postId}`,
      });
      return;
    }

    if (this.data.isRegistered) {
      // 取消报名
      wx.showModal({
        title: '确认取消',
        content: '确定取消报名吗？',
        success: async (res) => {
          if (res.confirm) {
            try {
              await app.request({
                url: `/posts/${this.data.postId}/register`,
                method: 'DELETE',
              });
              wx.showToast({ title: '已取消', icon: 'success' });
              this.loadPost(this.data.postId);
            } catch (e) {
              wx.showToast({ title: '操作失败', icon: 'none' });
            }
          }
        },
      });
    } else {
      // 报名
      wx.showModal({
        title: '确认报名',
        content: `确定报名参加「${this.data.post.title}」吗？`,
        success: async (res) => {
          if (res.confirm) {
            try {
              await app.request({
                url: `/posts/${this.data.postId}/register`,
                method: 'POST',
                data: { message: '' },
              });
              wx.showToast({ title: '报名成功', icon: 'success' });
              this.loadPost(this.data.postId);
            } catch (e) {
              const msg = (e.data && e.data.detail) || '报名失败';
              wx.showToast({ title: msg, icon: 'none' });
            }
          }
        },
      });
    }
  },

  onShowRegistrations() {
    this.setData({ showRegPopup: true });
  },

  onCloseRegPopup() {
    this.setData({ showRegPopup: false });
  },

  onRegPanelTap() {
    // prevent bubbling
  },

  onCallPhone() {
    const phone = (this.data.post && this.data.post.user_phone);
    if (phone) {
      wx.makePhoneCall({ phoneNumber: phone });
    } else {
      wx.showToast({ title: '暂无电话', icon: 'none' });
    }
  },

  onOpenMap() {
    const post = this.data.post;
    if (post && post.venue_latitude && post.venue_longitude) {
      wx.openLocation({
        latitude: parseFloat(post.venue_latitude),
        longitude: parseFloat(post.venue_longitude),
        name: post.club_name,
        address: post.venue_address,
      });
    } else {
      wx.showToast({ title: '暂无位置信息', icon: 'none' });
    }
  },

  onShareAppMessage() {
    const post = this.data.post;
    return {
      title: post && post.title || '约球帖',
      path: `/pages/common/post-detail?id=${this.data.postId}`,
    };
  },

  onOpenDocument(e) {
    const { url, name } = e.currentTarget.dataset;
    wx.showLoading({ title: '加载中...' });
    wx.downloadFile({
      url,
      success: (res) => {
        wx.hideLoading();
        if (res.statusCode === 200) {
          wx.openDocument({
            filePath: res.tempFilePath,
            fileType: 'pdf',
            showMenu: true,
          });
        }
      },
      fail: () => {
        wx.hideLoading();
        wx.showToast({ title: '下载失败', icon: 'none' });
      }
    });
  },

  onPullDownRefresh() {
    this.loadPost(this.data.postId).then(() => {
      wx.stopPullDownRefresh();
    });
  },
});
