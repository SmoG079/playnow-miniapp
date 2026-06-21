const app = getApp();

Page({
  data: {
    post: null,
    loading: true,
    isRegistered: false,
    myRegistrationStatus: '',
    isFull: false,
    isOwner: false,
    registrations: [],
    showRegPopup: false,

    comments: [],
    commentLoading: false,
    commentInput: '',
    replyTo: null, // { id, nickname }
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
      const isRegistered = post.registrations && post.registrations.some(r => r.user_id === currentUserId && ['pending', 'approved'].includes(r.status));
      const myRegistration = isRegistered ? post.registrations.find(r => r.user_id === currentUserId) : null;
      const isFull = post.registration_count >= post.players_needed;

      // Compute weekday from preferred_date
      if (post.preferred_date) {
        const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
        const d = new Date(post.preferred_date + 'T00:00:00');
        post.weekday = days[d.getDay()];
      } else {
        post.weekday = '';
      }

      this.setData({
        post,
        isOwner,
        isRegistered,
        myRegistrationStatus: myRegistration ? myRegistration.status : '',
        isFull,
        registrations: post.registrations || [],
        loading: false,
      });
      this.loadComments();
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  onRegister() {
    // Must be logged in to register/cancel/manage registrations
    if (!app.requireLogin({ redirect: `/pages/common/post-detail?id=${this.data.postId}` })) {
      return;
    }

    if (this.data.isOwner) {
      // 管理报名 - 跳转到审核页面
      wx.navigateTo({
        url: `/pages/publish/post-registration-approve?postId=${this.data.postId}`,
      });
      return;
    }

    if (this.data.isRegistered) {
      // 取消报名
      const statusText = this.data.myRegistrationStatus === 'pending' ? '待审核' : '已通过';
      wx.showModal({
        title: '确认取消',
        content: `确定取消${statusText}的报名吗？`,
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
              const msg = this.data.post.approval_required ? '报名已提交，等待审核' : '报名成功';
              wx.showToast({ title: msg, icon: 'success' });
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

  onMore() {
    wx.showActionSheet({
      itemList: ['举报', '复制链接', '取消'],
      success: (res) => {
        if (res.tapIndex === 1) {
          wx.setClipboardData({
            data: `/pages/common/post-detail?id=${this.data.postId}`,
          });
        }
      },
    });
  },

  onOpenChat() {
    if (!app.requireLogin({ redirect: `/pages/common/post-detail?id=${this.data.postId}` })) {
      return;
    }
    const post = this.data.post;
    if (post && post.group_chat_id) {
      wx.showToast({ title: '群聊功能待接入', icon: 'none' });
    } else {
      wx.showToast({ title: '暂无群聊', icon: 'none' });
    }
  },

  async loadComments() {
    this.setData({ commentLoading: true });
    try {
      const res = await app.request({ url: `/posts/${this.data.postId}/comments?page=1&page_size=50` });
      this.setData({ comments: res.items || [] });
    } catch (e) {
      console.error('Load comments failed', e);
    } finally {
      this.setData({ commentLoading: false });
    }
  },

  onCommentInput(e) {
    this.setData({ commentInput: e.detail.value });
  },

  onReplyTap(e) {
    const { id, nickname } = e.currentTarget.dataset;
    this.setData({ replyTo: { id, nickname } });
  },

  onCancelReply() {
    this.setData({ replyTo: null });
  },

  async onSubmitComment() {
    if (!app.requireLogin({ redirect: `/pages/common/post-detail?id=${this.data.postId}` })) {
      return;
    }
    const content = (this.data.commentInput || '').trim();
    if (!content) {
      return wx.showToast({ title: '请输入评论内容', icon: 'none' });
    }
    try {
      await app.request({
        url: `/posts/${this.data.postId}/comments`,
        method: 'POST',
        data: {
          content,
          parent_id: this.data.replyTo ? this.data.replyTo.id : null,
        },
      });
      this.setData({ commentInput: '', replyTo: null });
      this.loadComments();
    } catch (e) {
      wx.showToast({ title: '评论失败', icon: 'none' });
    }
  },

  onCommentLongPress(e) {
    const { id, userid } = e.currentTarget.dataset;
    const currentUserId = app.globalData.userInfo && app.globalData.userInfo.id;
    const isOwner = this.data.isOwner;
    const isAuthor = userid === currentUserId;
    if (!isAuthor && !isOwner) return;

    wx.showActionSheet({
      itemList: ['删除'],
      success: (res) => {
        if (res.tapIndex === 0) {
          this.deleteComment(id);
        }
      },
    });
  },

  async deleteComment(commentId) {
    if (!app.requireLogin({ redirect: `/pages/common/post-detail?id=${this.data.postId}` })) {
      return;
    }
    try {
      await app.request({
        url: `/posts/${this.data.postId}/comments/${commentId}`,
        method: 'DELETE',
      });
      wx.showToast({ title: '已删除', icon: 'success' });
      this.loadComments();
    } catch (e) {
      wx.showToast({ title: '删除失败', icon: 'none' });
    }
  },
});
