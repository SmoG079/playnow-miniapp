const app = getApp();

Page({
  data: {
    name: '',
    description: '',
    address: '',
    phone: '',
    loading: false,
  },

  onNameInput(e) { this.setData({ name: e.detail.value }); },
  onDescInput(e) { this.setData({ description: e.detail.value }); },
  onAddrInput(e) { this.setData({ address: e.detail.value }); },
  onPhoneInput(e) { this.setData({ phone: e.detail.value }); },

  async onSubmit() {
    if (!this.data.name) return wx.showToast({ title: '请输入名称', icon: 'none' });
    this.setData({ loading: true });
    try {
      await app.request({
        url: '/clubs',
        method: 'POST',
        data: {
          name: this.data.name,
          sport_types: ['tennis'],
          description: this.data.description,
          address: this.data.address,
          contact_phone: this.data.phone,
        },
      });
      wx.showToast({ title: '创建成功', icon: 'success' });
      // Refresh user info to get new role
      await app.fetchUserInfo();
      setTimeout(() => wx.switchTab({ url: '/pages/booking/club-list' }), 1500);
    } catch (e) {
      console.error(e);
    } finally {
      this.setData({ loading: false });
    }
  },
});
