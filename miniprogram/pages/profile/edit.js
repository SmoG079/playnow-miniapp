const app = getApp();

Page({
  data: {
    nickname: '',
    avatarUrl: '',
    ntrpLevel: '',
    ntrpLevels: ['1.0', '1.5', '2.0', '2.5', '3.0', '3.5', '4.0', '4.5', '5.0', '5.5', '6.0', '6.5', '7.0'],
    ntrpIndex: -1,
    loading: false,
  },

  onLoad() {
    const userInfo = app.globalData.userInfo || {};
    const ntrp = userInfo.ntrp_level;
    let ntrpIndex = -1;
    if (ntrp) {
      ntrpIndex = this.data.ntrpLevels.indexOf(String(ntrp));
    }
    this.setData({
      nickname: userInfo.nickname || '',
      avatarUrl: userInfo.avatar_url || '',
      ntrpLevel: ntrp ? String(ntrp) : '',
      ntrpIndex,
    });
  },

  onNicknameInput(e) {
    this.setData({ nickname: e.detail.value });
  },

  onNtrpChange(e) {
    const idx = parseInt(e.detail.value);
    this.setData({
      ntrpIndex: idx,
      ntrpLevel: this.data.ntrpLevels[idx],
    });
  },

  async chooseAvatar() {
    try {
      const res = await wx.chooseMedia({
        count: 1,
        mediaType: ['image'],
        sourceType: ['album', 'camera'],
      });
      const tempPath = res.tempFiles[0].tempFilePath;
      this.setData({ avatarUrl: tempPath });
    } catch (e) {
      console.error('Choose avatar failed', e);
    }
  },

  async onSubmit() {
    this.setData({ loading: true });
    try {
      let avatarUrl = this.data.avatarUrl;
      // Upload avatar if changed
      if (avatarUrl && !avatarUrl.startsWith('http')) {
        const res = await app.uploadFile(avatarUrl);
        avatarUrl = res.url;
      }

      const updateData = {};
      if (this.data.nickname) updateData.nickname = this.data.nickname;
      if (avatarUrl && avatarUrl.startsWith('http')) updateData.avatar_url = avatarUrl;
      if (this.data.ntrpLevel) updateData.ntrp_level = parseFloat(this.data.ntrpLevel);

      await app.request({
        url: '/users/me',
        method: 'PUT',
        data: updateData,
      });

      // Refresh user info
      await app.fetchUserInfo();

      wx.showToast({ title: '保存成功', icon: 'success' });
      setTimeout(() => wx.navigateBack(), 1000);
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },
});
