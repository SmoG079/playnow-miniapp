const app = getApp();

Component({
  data: {
    selected: 0,
    showActionSheet: false,
    selectedColor: '#07c160',
    defaultColor: '#999999',
    list: [
      { pagePath: '/pages/home/index', text: '首页', icon: '\u{1F3E0}' },
      { pagePath: '/pages/booking/club-list', text: '订场', icon: '\u{1F4CD}' },
      { pagePath: '', text: '', icon: 'plus' },
      { pagePath: '/pages/chat/index', text: '消息', icon: '\u{1F4AC}' },
      { pagePath: '/pages/profile/index', text: '我的', icon: '\u{1F464}' },
    ],
    actionSheetItems: [],
  },

  methods: {
    switchTab(e) {
      const index = e.currentTarget.dataset.index;
      const item = this.data.list[index];
      if (index === 2) {
        this.openActionSheet();
        return;
      }
      wx.switchTab({ url: item.pagePath });
    },

    openActionSheet() {
      const isAdmin = app.isClubAdmin();
      const hasClub = app.globalData.managedClubIds.length > 0;

      const items = [
        { label: '发布约球帖', icon: '\u{1F4DD}', page: '/pages/publish/post-create', show: hasClub },
        { label: '创建俱乐部', icon: '\u{1F3E2}', page: '/pages/publish/club-create', show: !hasClub },
        { label: '发布比赛', icon: '\u{1F3C6}', page: '/pages/publish/tournament-create', show: isAdmin && hasClub },
        { label: '管理场地', icon: '⚙', page: '/pages/publish/venue-manage', show: isAdmin && hasClub },
        { label: '管理订单', icon: '\u{1F4CB}', page: '/pages/publish/order-manage', show: isAdmin && hasClub },
      ];

      this.setData({
        showActionSheet: true,
        actionSheetItems: items.filter(i => i.show),
      });
    },

    closeActionSheet() {
      this.setData({ showActionSheet: false });
    },

    onActionTap(e) {
      const page = e.currentTarget.dataset.page;
      this.closeActionSheet();
      if (!page) return;
      // TabBar pages must use switchTab
      if (page === '/pages/publish/post-create') {
        wx.switchTab({ url: page });
      } else {
        wx.navigateTo({ url: page });
      }
    },

    onMaskTap() { this.closeActionSheet(); },
    onContainerTap() {},
  },
});
