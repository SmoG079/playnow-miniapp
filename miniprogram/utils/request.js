/**
 * HTTP request wrapper with token auto-refresh.
 * Alternative to using app.request() directly.
 */
const app = getApp();

function request(url, options = {}) {
  const { method = 'GET', data = {}, skipAuth = false } = options;

  return new Promise((resolve, reject) => {
    const header = {};
    if (!skipAuth && app.globalData.token) {
      header['Authorization'] = `Bearer ${app.globalData.token}`;
    }

    wx.request({
      url: app.globalData.baseURL + url,
      method,
      data,
      header,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else if (res.statusCode === 401) {
          // Trigger token refresh in app.js
          app.refreshTokenAndRetry({ url, method, data, resolve, reject });
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
}

module.exports = { request };
