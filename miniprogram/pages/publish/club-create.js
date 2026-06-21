const app = getApp();

Page({
  data: {
    name: '',
    description: '',
    rules: '',
    address: '',
    addressName: '',
    latitude: null,
    longitude: null,
    phone: '',
    images: [],
    documents: [],
    loading: false,
    submitDisabled: true,
  },

  onLoad() {
    this._updateSubmitDisabled();
  },

  async onSubmit() {
    if (!this.data.name) return wx.showToast({ title: '请输入名称', icon: 'none' });
    if (!this.data.phone) return wx.showToast({ title: '请输入联系电话', icon: 'none' });
    if (!/^1\d{10}$/.test(this.data.phone) && !/^\d{7,12}$/.test(this.data.phone)) {
      return wx.showToast({ title: '联系电话格式不正确', icon: 'none' });
    }
    if (!this.data.address) return wx.showToast({ title: '请输入地址', icon: 'none' });
    if (!this.data.latitude || !this.data.longitude) {
      // Manual address without map coordinates: try backend geocoder (best effort)
      try {
        const geocoded = await this._geocodeAddress(this.data.address);
        if (geocoded && geocoded.latitude != null && geocoded.longitude != null) {
          this.setData({ latitude: geocoded.latitude, longitude: geocoded.longitude });
        } else {
          // No key configured or geocoder failed: allow creation without coordinates
          this.setData({ latitude: null, longitude: null });
        }
      } catch (e) {
        console.error('Geocode failed', e);
        this.setData({ latitude: null, longitude: null });
      }
    }
    this.setData({ loading: true });
    try {
      // 先上传图片和PDF
      const [images, documents] = await Promise.all([
        this.uploadImages(),
        this.uploadDocuments(),
      ]);

      await app.request({
        url: '/clubs',
        method: 'POST',
        data: {
          name: this.data.name,
          sport_types: ['tennis'],
          description: this.data.description,
          rules: this.data.rules,
          address: this.data.address,
          latitude: this.data.latitude,
          longitude: this.data.longitude,
          contact_phone: this.data.phone,
          images,
          documents,
        },
      });
      wx.showToast({ title: '创建成功', icon: 'success' });
      await app.fetchUserInfo();
      setTimeout(() => wx.switchTab({ url: '/pages/booking/club-list' }), 1500);
    } catch (e) {
      console.error(e);
      wx.showToast({ title: e.message || '创建失败', icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },
});
