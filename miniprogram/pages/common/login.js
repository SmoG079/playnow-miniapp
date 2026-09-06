const app = getApp();
const auth = require('../../utils/auth');

Page({
  data: {
    loading: false,
    agreed: false,
    redirect: '',
  },

  onLoad(options) {
    if (app.globalData.token) {
      wx.switchTab({ url: '/pages/home/index' });
      return;
    }
    if (options && options.redirect) {
      this.setData({ redirect: decodeURIComponent(options.redirect) });
    }
  },

  onAgreementChange() {
    this.setData({ agreed: !this.data.agreed });
  },

  async onLogin() {
    if (this.data.loading) return;
    if (!this.data.agreed) {
      wx.showToast({ title: '请先同意用户协议', icon: 'none' });
      return;
    }

    this.setData({ loading: true });
    try {
      const userInfo = await auth.login();

      // New user without nickname → go to edit profile
      if (!userInfo.nickname) {
        wx.reLaunch({ url: '/pages/profile/edit?new_user=1&redirect=' + encodeURIComponent(this.data.redirect) });
        return;
      }

      // Returning user → go home or redirect
      const redirect = this.data.redirect;
      if (redirect && redirect.startsWith('/pages/')) {
        app.openPage(redirect);
      } else {
        wx.switchTab({ url: '/pages/home/index' });
      }
    } catch (e) {
      wx.showToast({ title: '登录失败，请重试', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },
});
