App({
  globalData: {
    userInfo: null,
    token: null,
    refreshToken: null,
    role: 'user',           // 'user' | 'club_admin' | 'platform_admin'
    managedClubIds: [],      // clubs this user manages
    baseURL: 'http://localhost/api/v1',
  },

  onLaunch() {
    // Restore login state from storage
    const token = wx.getStorageSync('access_token');
    const refreshToken = wx.getStorageSync('refresh_token');
    if (token) {
      this.globalData.token = token;
      this.globalData.refreshToken = refreshToken;
      this.fetchUserInfo();
    }
  },

  /** Redirect to login if not authenticated. Returns true if logged in. */
  requireLogin() {
    if (this.globalData.token) return true;
    wx.navigateTo({ url: '/pages/common/login' });
    return false;
  },

  async fetchUserInfo() {
    try {
      const res = await this.request({ url: '/users/me' });
      this.globalData.userInfo = res;
      this.globalData.role = res.role;
      this.globalData.managedClubIds = res.managed_club_ids || [];
    } catch (e) {
      console.error('Fetch user info failed', e);
    }
  },

  request({ url, method = 'GET', data = {}, skipAuth = false }) {
    return new Promise((resolve, reject) => {
      const header = {};
      if (!skipAuth && this.globalData.token) {
        header['Authorization'] = `Bearer ${this.globalData.token}`;
      }
      wx.request({
        url: this.globalData.baseURL + url,
        method,
        data,
        header,
        timeout: 30000,
        success: (res) => {
          if (res.statusCode === 200) {
            resolve(res.data);
          } else if (res.statusCode === 401) {
            this.refreshTokenAndRetry({ url, method, data, resolve, reject });
          } else {
            wx.showToast({ title: (res.data && res.data.detail) || '请求失败', icon: 'none' });
            reject(res);
          }
        },
        fail: (err) => {
          wx.showToast({ title: '网络错误', icon: 'none' });
          reject(err);
        },
      });
    });
  },

  async refreshTokenAndRetry({ url, method, data, resolve, reject }) {
    try {
      const res = await this.request({
        url: '/auth/refresh',
        method: 'POST',
        data: { refresh_token: this.globalData.refreshToken },
        skipAuth: true,
      });
      this.globalData.token = res.access_token;
      this.globalData.refreshToken = res.refresh_token;
      wx.setStorageSync('access_token', res.access_token);
      wx.setStorageSync('refresh_token', res.refresh_token);
      // Retry original request
      const retryRes = await this.request({ url, method, data });
      resolve(retryRes);
    } catch (e) {
      // Refresh failed, go to login
      wx.removeStorageSync('access_token');
      wx.removeStorageSync('refresh_token');
      wx.reLaunch({ url: '/pages/common/login' });
      reject(e);
    }
  },

  /** Check if user is a club admin */
  isClubAdmin() {
    return this.globalData.role === 'club_admin' || this.globalData.role === 'platform_admin';
  },

  /** Upload file to OSS */
  uploadFile(filePath) {
    return new Promise((resolve, reject) => {
      wx.uploadFile({
        url: this.globalData.baseURL + '/upload',
        filePath,
        name: 'file',
        header: {
          'Authorization': `Bearer ${this.globalData.token}`,
        },
        success: (res) => {
          if (res.statusCode === 200) {
            resolve(JSON.parse(res.data));
          } else {
            reject(new Error('上传失败'));
          }
        },
        fail: reject,
      });
    });
  },

  /** Get user location */
  getUserLocation() {
    return new Promise((resolve, reject) => {
      wx.getLocation({
        type: 'gcj02',
        success: (res) => {
          const loc = { latitude: res.latitude, longitude: res.longitude };
          this.globalData.userLocation = loc;
          resolve(loc);
        },
        fail: (err) => {
          console.error('Get location failed', err);
          reject(err);
        },
      });
    });
  },

  /** Check if user manages a specific club */
  managesClub(clubId) {
    return this.globalData.managedClubIds.includes(clubId);
  },
});
