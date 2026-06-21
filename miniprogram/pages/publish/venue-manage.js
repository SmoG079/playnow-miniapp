const app = getApp();

Page({
  data: {
    clubId: null,
    venues: [],
    loading: false,
    showForm: false,
    formTitle: '添加场地',
    editingVenue: null,
    formData: {
      name: '',
      price_per_hour: '',
      open_time: '08:00',
      close_time: '22:00',
    },
  },

  async onShow() {
    // Ensure user info is fresh so managedClubIds is populated
    await app.fetchUserInfo();
    const clubIds = app.globalData.managedClubIds || [];
    if (clubIds.length === 0) {
      wx.showToast({ title: '请先创建俱乐部', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 1500);
      return;
    }
    this.setData({ clubId: clubIds[0] });
    this.loadVenues();
  },

  async loadVenues() {
    this.setData({ loading: true });
    try {
      const res = await app.request({ url: `/clubs/${this.data.clubId}/venues` });
      this.setData({ venues: res || [] });
    } catch (e) {
      console.error('Load venues failed', e);
    } finally {
      this.setData({ loading: false });
    }
  },

  onShowForm(e) {
    const venue = e?.currentTarget?.dataset?.venue;
    this.setData({
      showForm: true,
      formTitle: venue ? '编辑场地' : '添加场地',
      editingVenue: venue || null,
      formData: venue ? {
        name: venue.name,
        price_per_hour: String(venue.price_per_hour),
        open_time: venue.open_time || '08:00',
        close_time: venue.close_time || '22:00',
      } : { name: '', price_per_hour: '', open_time: '08:00', close_time: '22:00' },
    });
  },

  onHideForm() {
    this.setData({ showForm: false });
  },

  onFieldInput(e) {
    const field = e.currentTarget.dataset.field;
    const val = e.detail.value;
    this.setData({ [`formData.${field}`]: val });
  },

  onTimeChange(e) {
    const field = e.currentTarget.dataset.field;
    this.setData({ [`formData.${field}`]: e.detail.value });
  },

  async onSaveVenue() {
    const f = this.data.formData;
    if (!f.name) return wx.showToast({ title: '请输入场地名称', icon: 'none' });
    if (!f.price_per_hour || parseFloat(f.price_per_hour) <= 0) {
      return wx.showToast({ title: '请输入有效价格', icon: 'none' });
    }
    if (!f.open_time || !f.close_time) {
      return wx.showToast({ title: '请设置营业时间', icon: 'none' });
    }

    try {
      if (this.data.editingVenue) {
        wx.showToast({ title: '编辑功能即将上线', icon: 'none' });
        return;
      } else {
        await app.request({
          url: `/venues/with-club/${this.data.clubId}`,
          method: 'POST',
          data: {
            name: f.name,
            price_per_hour: parseFloat(f.price_per_hour),
            open_time: f.open_time,
            close_time: f.close_time,
          },
        });
      }
      wx.showToast({ title: '创建成功，已自动生成时段', icon: 'success' });
      this.setData({ showForm: false });
      this.loadVenues();
    } catch (e) {
      console.error('Save venue failed', e);
    }
  },

  onDeleteVenue(e) {
    wx.showToast({ title: '删除功能即将上线', icon: 'none' });
  },
});
