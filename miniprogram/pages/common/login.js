const app = getApp();
const auth = require('../../utils/auth');

Page({
  data: {
    loading: false,
    agreed: false,
    redirect: '',
    nickname: '',
    avatarUrl: '',
  },

  onLoad(options) {
    // If already logged in, redirect to home
    if (app.globalData.token) {
      wx.switchTab({ url: '/pages/home/index' });
    }
    // Remember the page that triggered login so we can navigate back after success
    if (options && options.redirect) {
      this.setData({ redirect: decodeURIComponent(options.redirect) });
    }
  },

  onAgreementChange() {
    this.setData({ agreed: !this.data.agreed });
  },

  onNicknameInput(e) {
    this.setData({ nickname: e.detail.value });
  },

  async onLogin() {
    if (!this.data.agreed) {
      wx.showToast({ title: '请先同意用户协议', icon: 'none' });
      return;
    }

    this.setData({ loading: true });
    try {
      await auth.login();

      // Sync nickname and avatar to backend if provided
      const updates = {};
      if (this.data.nickname) {
        updates.nickname = this.data.nickname;
      }
      if (this.data.avatarUrl) {
        updates.avatar_url = this.data.avatarUrl;
      }
      if (Object.keys(updates).length > 0) {
        await app.request({
          url: '/users/me',
          method: 'PUT',
          data: updates,
        });
        // Refresh cached user info
        await app.fetchUserInfo();
      }

      const redirect = this.data.redirect;
      if (redirect) {
        // Redirect back to the page that required login. Use reLaunch for non-tab pages
        // and switchTab for tab pages to avoid navigation stack issues.
        if (redirect.startsWith('/pages/') && redirect.includes('?')) {
          wx.reLaunch({ url: redirect });
        } else if (redirect.startsWith('/pages/')) {
          const tabPages = ['/pages/home/index', '/pages/profile/index'];
          if (tabPages.includes(redirect)) {
            wx.switchTab({ url: redirect });
          } else {
            wx.reLaunch({ url: redirect });
          }
        } else {
          wx.switchTab({ url: '/pages/home/index' });
        }
      } else {
        wx.switchTab({ url: '/pages/home/index' });
      }
    } catch (e) {
      wx.showToast({ title: '登录失败，请重试', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  // WeChat native avatar picker callback
  onChooseAvatar(e) {
    const { avatarUrl } = e.detail;
    this.setData({ avatarUrl });
    // Upload to OSS and save to profile
    console.log('Avatar chosen:', avatarUrl);
  },

  // WeChat phone number callback
  onGetPhoneNumber(e) {
    const { code } = e.detail;
    if (!code) {
      wx.showToast({ title: '授权手机号失败', icon: 'none' });
      return;
    }
    app.request({
      url: '/auth/phone',
      method: 'POST',
      data: { code },
    }).then(() => {
      wx.showToast({ title: '手机号已保存', icon: 'success' });
    }).catch(err => {
      console.error('Phone failed:', err);
      wx.showToast({ title: '手机号保存失败', icon: 'none' });
    });
  },
});
