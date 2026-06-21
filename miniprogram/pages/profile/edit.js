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
    const phoneCode = code || 'dev_phone';
    if (!code) console.warn('getPhoneNumber fallback:', errMsg);
    app.request({
      url: '/auth/phone', method: 'POST', data: { code: phoneCode },
    }).then(() => {
      wx.showToast({ title: '已获取手机号', icon: 'success' });
      app.fetchUserInfo().then(() => {
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
    this.setData({ loading: true });
    try {
      const updateData = {};
      if (this.data.nickname) updateData.nickname = this.data.nickname;
      if (this.data.phone) updateData.phone = this.data.phone;
      if (this.data.avatarUrl) updateData.avatar_url = this.data.avatarUrl;
      if (this.data.ntrpLevel) updateData.ntrp_level = parseFloat(this.data.ntrpLevel);

      await app.request({
        url: '/users/me',
        method: 'PUT',
        data: updateData,
      });

      await app.fetchUserInfo();
      wx.showToast({ title: '保存成功', icon: 'success' });
      if (this.data.isNewUser) {
        setTimeout(() => wx.switchTab({ url: '/pages/home/index' }), 1000);
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
