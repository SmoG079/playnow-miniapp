const app = getApp();
const auth = require('../../utils/auth');

Page({
  data: {
    loading: false,
    agreed: false,
  },

  onLoad() {
    // If already logged in, redirect to home
    if (app.globalData.token) {
      wx.switchTab({ url: '/pages/home/index' });
    }
  },

  onAgreementChange() {
    this.setData({ agreed: !this.data.agreed });
  },

  async onLogin() {
    if (!this.data.agreed) {
      wx.showToast({ title: '请先同意用户协议', icon: 'none' });
      return;
    }

    this.setData({ loading: true });
    try {
      await auth.login();
      wx.switchTab({ url: '/pages/home/index' });
    } catch (e) {
      wx.showToast({ title: '登录失败，请重试', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  // WeChat native avatar picker callback
  onChooseAvatar(e) {
    const { avatarUrl } = e.detail;
    // Upload to OSS and save to profile
    console.log('Avatar chosen:', avatarUrl);
  },

  // WeChat phone number callback
  onGetPhoneNumber(e) {
    auth.getPhoneNumber(e).then(() => {
      console.log('Phone saved');
    }).catch(err => {
      console.error('Phone failed:', err);
    });
  },
});
