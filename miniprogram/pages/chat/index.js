Page({
  data: {
    conversations: [],
    unreadCount: 0,
  },

  onShow() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 3 });
    }
    // TODO: Load conversations from backend
  },

  onContactService() {
    wx.showToast({ title: '客服暂未接通', icon: 'none' });
  },

  onNotifications() { wx.navigateTo({ url: '/pages/message/list' }); },

  onConversationTap(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/chat/conversation?id=${id}` });
  },

  onCreateGroup() {
    // Guide user to create WeChat group chat
    wx.showModal({
      title: '创建群聊',
      content: '将通过微信创建群聊，是否继续？',
      success: (res) => {
        if (res.confirm) {
          // Use WeChat's group chat capability
          wx.navigateToMiniProgram({
            appId: '', // WeChat group chat app ID
            fail: () => {
              wx.showToast({ title: '请在微信中创建群聊', icon: 'none' });
            },
          });
        }
      },
    });
  },
});
