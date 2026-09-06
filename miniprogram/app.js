const { baseURL, env } = require('./config');

App({
  globalData: {
    userInfo: null,
    token: null,
    refreshToken: null,
    role: 'user',           // 'user' | 'club_admin' | 'platform_admin'
    managedClubIds: [],      // clubs this user manages
    baseURL,
    env,
  },

  onLaunch() {
    // Restore login state from storage
    const token = wx.getStorageSync('access_token');
    const refreshToken = wx.getStorageSync('refresh_token');
    if (token) {
      this.globalData.token = token;
      this.globalData.refreshToken = refreshToken;
      this.fetchUserInfo().catch(e => console.error('Restore session failed', e));
    }
  },

  /** Redirect to login if not authenticated. Returns true if logged in. */
  clearSession() {
    Object.assign(this.globalData, { token: null, refreshToken: null, userInfo: null, role: 'user', managedClubIds: [], _bookingReturn: null });
    wx.removeStorageSync('access_token');
    wx.removeStorageSync('refresh_token');
  },

  openPage(url) {
    const tabs = ['/pages/home/index', '/pages/booking/club-list', '/pages/publish/post-create', '/pages/chat/index', '/pages/profile/index'];
    if (tabs.includes(url.split('?')[0])) wx.switchTab({ url: url.split('?')[0] });
    else wx.reLaunch({ url });
  },

  requireLogin(options = {}) {
    if (this.globalData.token) return true;
    const { redirect } = options;
    const url = redirect
      ? `/pages/common/login?redirect=${encodeURIComponent(redirect)}`
      : '/pages/common/login';
    wx.navigateTo({ url });
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
      throw e;
    }
  },

  async listAll(url) {
    const items = [];
    for (let page = 1; ; page++) {
      const res = await this.request({ url: `${url}${url.includes('?') ? '&' : '?'}page=${page}&page_size=50` });
      const batch = res.items || [];
      items.push(...batch);
      if (batch.length < 50 || (typeof res.total === 'number' && items.length >= res.total)) return items;
    }
  },

  request({ url, method = 'GET', data = {}, skipAuth = false, skipRefresh = false }) {
    return new Promise((resolve, reject) => {
      const header = {};
      if (!skipAuth && this.globalData.token) {
        header['Authorization'] = `Bearer ${this.globalData.token}`;
      }
      wx.request({
        url: this.globalData.baseURL + url,
        method,
        data,
        header: {
          ...header,
          'Content-Type': 'application/json',
        },
        timeout: 30000,
        success: (res) => {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(res.data);
          } else if (res.statusCode === 401 && !skipRefresh && !skipAuth) {
            this.refreshTokenAndRetry({ url, method, data, resolve, reject });
          } else {
            const detail = res.data && res.data.detail;
            const title = typeof detail === 'string' ? detail : (Array.isArray(detail) ? detail.map(item => item.msg || '参数错误').join('；') : '请求失败');
            wx.showToast({ title, icon: 'none' });
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
      if (!this._refreshPromise) this._refreshPromise = this.request({
        url: '/auth/refresh',
        method: 'POST',
        data: { refresh_token: this.globalData.refreshToken },
        skipAuth: true,
        skipRefresh: true,
      }).then(res => {
        this.globalData.token = res.access_token;
        this.globalData.refreshToken = res.refresh_token;
        wx.setStorageSync('access_token', res.access_token);
        wx.setStorageSync('refresh_token', res.refresh_token);
      }).finally(() => { this._refreshPromise = null; });
      await this._refreshPromise;
    } catch (e) {
      // Refresh failed, go to login
      this.clearSession();
      wx.reLaunch({ url: '/pages/common/login' });
      reject(e);
      return;
    }
    // A business/network error after refresh must not discard a valid session.
    try { resolve(await this.request({ url, method, data, skipRefresh: true })); }
    catch (e) { reject(e); }
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
            try {
              const body = JSON.parse(res.data);
              if (!body.url) throw new Error('上传响应缺少文件地址');
              resolve(body);
            } catch (e) { reject(e); }
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
