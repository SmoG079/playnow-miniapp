const app = getApp();

Page({
  data: {
    nickname: '',
    phone: '',
    ntrpLevel: '',
    ntrpLevels: ['1.0', '1.5', '2.0', '2.5', '3.0', '3.5', '4.0', '4.5', '5.0', '5.5', '6.0', '6.5', '7.0'],
    ntrpIndex: -1,
    isNewUser: false,
    loading: false,
  },

  onLoad(options) {
    if (!app.requireLogin()) return;
    this.setData({ redirect: options.redirect ? decodeURIComponent(options.redirect) : '' });
    if (options.new_user === '1') {
      this.setData({ isNewUser: true });
      wx.setNavigationBarTitle({ title: '完善资料' });
    }
    const userInfo = app.globalData.userInfo || {};
    const ntrp = userInfo.ntrp_level;
    let ntrpIndex = -1;
    if (ntrp) {
      ntrpIndex = this.data.ntrpLevels.indexOf(String(ntrp));
    }
    this.setData({
      phone: userInfo.phone || '',
      nickname: userInfo.nickname || '',
      avatarUrl: userInfo.avatar_url || '',
      ntrpLevel: ntrp ? String(ntrp) : '',
      ntrpIndex,
    });
  },

  onChooseAvatar(e) {
    this.setData({ avatarUrl: e.detail.avatarUrl });
  },

  onNicknameInput(e) {
    this.setData({ nickname: e.detail.value });
  },

  onPhoneInput(e) {
    this.setData({ phone: e.detail.value });
  },

  onGetPhoneNumber(e) {
    const { code, errMsg } = e.detail;
    if (!code) {
      wx.showToast({ title: '未授权手机号，可手动填写', icon: 'none' });
      return;
    }
    app.request({
      url: '/auth/phone', method: 'POST', data: { code },
    }).then(() => {
      wx.showToast({ title: '已获取手机号', icon: 'success' });
      return app.fetchUserInfo().then(() => {
        const phone = (app.globalData.userInfo || {}).phone;
        if (phone) this.setData({ phone });
      });
    }).catch(err => {
      console.error('Phone failed:', err);
      wx.showToast({ title: '手机号获取失败', icon: 'none' });
    });
  },

  onNtrpChange(e) {
    const idx = parseInt(e.detail.value);
    this.setData({
      ntrpIndex: idx,
      ntrpLevel: this.data.ntrpLevels[idx],
    });
  },

  async onSubmit() {
    if (this.data.loading) return;
    if (!this.data.nickname.trim()) return wx.showToast({ title: '请输入昵称', icon: 'none' });
    if (this.data.phone && !/^1\d{10}$/.test(this.data.phone)) return wx.showToast({ title: '手机号格式不正确', icon: 'none' });
    this.setData({ loading: true });
    try {
      const updateData = {};
      if (this.data.nickname) updateData.nickname = this.data.nickname;
      if (this.data.phone) updateData.phone = this.data.phone;
      if (this.data.avatarUrl) {
        updateData.avatar_url = /^https?:\/\//.test(this.data.avatarUrl)
          ? this.data.avatarUrl : (await app.uploadFile(this.data.avatarUrl)).url;
      }
      if (this.data.ntrpLevel) updateData.ntrp_level = parseFloat(this.data.ntrpLevel);

      await app.request({
        url: '/users/me',
        method: 'PUT',
        data: updateData,
      });

      await app.fetchUserInfo();
      wx.showToast({ title: '保存成功', icon: 'success' });
      if (this.data.isNewUser) {
        const redirect = this.data.redirect;
        setTimeout(() => app.openPage(redirect && redirect.startsWith('/pages/') ? redirect : '/pages/home/index'), 1000);
      } else {
        setTimeout(() => wx.navigateBack(), 1000);
      }
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },
});
