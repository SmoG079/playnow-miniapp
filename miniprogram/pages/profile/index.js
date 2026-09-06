const app = getApp();
const perm = require('../../utils/permission');

Page({
  data: {
    userInfo: null,
    role: 'user',
    managedClubIds: [],
    menuItems: [],
    isLoggedIn: false,
  },

  onShow() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 4 });
    }
    this.setData({ isLoggedIn: !!app.globalData.token });
    this.buildMenu();
  },

  onLogin() {
    wx.navigateTo({ url: '/pages/common/login' });
  },

  buildMenu() {
    const userInfo = app.globalData.userInfo || {};
    const role = app.globalData.role;
    const isAdmin = perm.isClubAdmin();
    const hasClub = perm.getManagedClubIds().length > 0;

    this.setData({
      userInfo,
      role,
      managedClubIds: perm.getManagedClubIds(),
    });

    // Dynamic menu based on role
    const commonMenu = [
      { icon: '📋', title: '我的预约', page: '/pages/profile/my-bookings' },
      { icon: '📝', title: '我的报名', page: '/pages/profile/my-registrations' },
      { icon: '📋', title: '活动管理', page: '/pages/profile/my-posts' },
      { icon: '📋', title: '系统通知', page: '/pages/message/list' },
    ];

    const adminMenu = [
      { icon: '🏠', title: '俱乐部管理', page: '/pages/profile/club-dashboard' },
      { icon: '💰', title: '分账记录', page: '/pages/profile/settlement-list' },
    ];

    const menu = [...commonMenu];
    if (isAdmin && hasClub) {
      menu.splice(1, 0, ...adminMenu);
    }

    this.setData({ menuItems: menu });
  },

  onMenuTap(e) {
    const page = e.currentTarget.dataset.page;
    if (page) {
      wx.navigateTo({ url: page });
    }
  },

  onImgError(e) {
    // Fallback: keep current src to avoid infinite loop
  },

  onEditProfile() {
    wx.navigateTo({ url: '/pages/profile/edit' });
  },

  onLogout() {
    wx.showModal({
      title: '退出登录',
      content: '确定要退出登录吗？',
      success: (res) => {
        if (res.confirm) {
          app.clearSession();
          this.setData({ isLoggedIn: false, userInfo: null });
          this.buildMenu();
          wx.showToast({ title: '已退出', icon: 'success' });
        }
      },
    });
  },

  onShareAppMessage() {
    return {
      title: '运动俱乐部 - 发现你的运动圈',
      path: '/pages/home/index',
    };
  },
});
