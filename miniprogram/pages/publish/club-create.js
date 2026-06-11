const app = getApp();

Page({
  data: {
    name: '',
    sportTypes: ['网球'],
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
  },

  onNameInput(e) { this.setData({ name: e.detail.value }); },
  onDescInput(e) { this.setData({ description: e.detail.value }); },
  onRulesInput(e) { this.setData({ rules: e.detail.value }); },
  onPhoneInput(e) { this.setData({ phone: e.detail.value }); },
  onAddressInput(e) { this.setData({ address: e.detail.value }); },

  // 选择地址（地图API）
  chooseLocation() {
    wx.chooseLocation({
      success: (res) => {
        this.setData({
          addressName: res.name,
          address: res.address || res.name || '',
          latitude: res.latitude,
          longitude: res.longitude,
        });
      },
      fail: (err) => {
        if (err.errMsg && err.errMsg.includes('auth deny')) {
          wx.showModal({
            title: '需要位置权限',
            content: '请在设置中开启位置权限',
            success: (r) => {
              if (r.confirm) wx.openSetting();
            }
          });
        } else if (err.errMsg && err.errMsg.includes('cancel')) {
          // User cancelled, do nothing
        } else {
          wx.showToast({ title: '选择地址失败，请手动输入', icon: 'none' });
        }
      }
    });
  },

  // 选择图片
  chooseImage() {
    const remain = 9 - this.data.images.length;
    if (remain <= 0) return wx.showToast({ title: '最多9张图片', icon: 'none' });
    wx.chooseMedia({
      count: remain,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const newImages = res.tempFiles.map(f => f.tempFilePath);
        this.setData({ images: [...this.data.images, ...newImages] });
      }
    });
  },

  // 预览图片
  previewImage(e) {
    const url = e.currentTarget.dataset.url;
    wx.previewImage({ current: url, urls: this.data.images });
  },

  // 删除图片
  removeImage(e) {
    const idx = e.currentTarget.dataset.idx;
    const images = [...this.data.images];
    images.splice(idx, 1);
    this.setData({ images });
  },

  // 上传图片到OSS
  async uploadImages() {
    const urls = [];
    for (const path of this.data.images) {
      if (path.startsWith('http')) {
        urls.push(path);
        continue;
      }
      const res = await app.uploadFile(path);
      urls.push(res.url);
    }
    return urls;
  },

  // 选择PDF文件（支持从聊天记录或相册选择）
  chooseDocument() {
    const remain = 5 - this.data.documents.length;
    if (remain <= 0) return wx.showToast({ title: '最多5个文件', icon: 'none' });
    wx.showActionSheet({
      itemList: ['从微信聊天记录选择', '从相册选择图片'],
      success: (res) => {
        if (res.tapIndex === 0) {
          this._chooseDocFromChat(remain);
        } else {
          this._chooseDocFromAlbum(remain);
        }
      }
    });
  },

  _chooseDocFromChat(remain) {
    wx.chooseMessageFile({
      count: remain,
      type: 'file',
      extension: ['pdf'],
      success: (res) => {
        this._processDocs(res.tempFiles);
      }
    });
  },

  _chooseDocFromAlbum(remain) {
    wx.chooseMedia({
      count: remain,
      mediaType: ['image'],
      sourceType: ['album'],
      success: (res) => {
        const files = res.tempFiles.map((f, i) => ({
          name: `文档图片_${i + 1}.jpg`,
          path: f.tempFilePath,
          size: f.size || 0,
        }));
        this._processDocs(files);
      }
    });
  },

  _processDocs(files) {
    const newDocs = files.map(f => ({
      name: f.name,
      path: f.path,
      size: f.size,
    }));
    for (const doc of newDocs) {
      if (doc.size > 10 * 1024 * 1024) {
        return wx.showToast({ title: `${doc.name} 超过10MB`, icon: 'none' });
      }
      doc.sizeStr = doc.size > 1024 * 1024
        ? (doc.size / 1024 / 1024).toFixed(1) + 'MB'
        : (doc.size / 1024).toFixed(0) + 'KB';
    }
    this.setData({ documents: [...this.data.documents, ...newDocs] });
  },

  // 删除PDF
  removeDocument(e) {
    const idx = e.currentTarget.dataset.idx;
    const documents = [...this.data.documents];
    documents.splice(idx, 1);
    this.setData({ documents });
  },

  // 上传PDF到OSS
  async uploadDocuments() {
    const docs = [];
    for (const doc of this.data.documents) {
      if (doc.url) {
        docs.push(doc);
        continue;
      }
      const res = await app.uploadFile(doc.path);
      docs.push({ name: doc.name, url: res.url, size: doc.size });
    }
    return docs;
  },

  async onSubmit() {
    if (!this.data.name) return wx.showToast({ title: '请输入名称', icon: 'none' });
    if (!this.data.latitude || !this.data.longitude) {
      return wx.showToast({ title: '请选择地址', icon: 'none' });
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
          sport_types: this.data.sportTypes,
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
