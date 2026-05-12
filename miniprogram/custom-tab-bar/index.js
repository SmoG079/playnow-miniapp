const app = getApp();

Component({
  data: {
    selected: 0,
    showActionSheet: false,
    color: '#999999',
    selectedColor: '#07c160',
    list: [
      { pagePath: '/pages/home/index', text: '首页', icon: 'home' },
      { pagePath: '/pages/booking/club-list', text: '订场', icon: 'location' },
      { pagePath: '', text: '', icon: 'plus' },
      { pagePath: '/pages/chat/index', text: '消息', icon: 'message' },
      { pagePath: '/pages/profile/index', text: '我的', icon: 'user' },
    ],
    // "+" action sheet menu items, populated dynamically
    actionSheetItems: [],
  },

  methods: {
    switchTab(e) {
      const index = e.currentTarget.dataset.index;
      const item = this.data.list[index];

      if (index === 2) {
        // Center "+" button -> open action sheet
        this.openActionSheet();
        return;
      }

      wx.switchTab({ url: item.pagePath });
    },

    openActionSheet() {
      const role = app.globalData.role;
      const isAdmin = app.isClubAdmin();
      const hasClub = app.globalData.managedClubIds.length > 0;

      const items = [
        { label: '发布约球帖', icon: 'post', page: '/pages/publish/post-create', show: true },
        { label: '创建俱乐部', icon: 'club', page: '/pages/publish/club-create', show: !hasClub },
        { label: '发布比赛', icon: 'trophy', page: '/pages/publish/tournament-create', show: isAdmin && hasClub },
        { label: '管理场地', icon: 'setting', page: '/pages/publish/venue-manage', show: isAdmin && hasClub },
        { label: '管理订单', icon: 'order', page: '/pages/publish/order-manage', show: isAdmin && hasClub },
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
      if (page) {
        wx.navigateTo({ url: page });
      }
    },

    // Prevent tap-through on mask
    onMaskTap() {
      this.closeActionSheet();
    },

    onContainerTap() {
      // Do nothing, prevent close when tapping sheet content
    },
  },
});
