const app = getApp();

/**
 * WeChat login flow:
 * 1. wx.login() -> get code
 * 2. Backend exchanges code for JWT
 * 3. Store tokens in storage + globalData
 */
async function login() {
  return new Promise((resolve, reject) => {
    wx.login({
      success: async (loginRes) => {
        try {
          const res = await app.request({
            url: '/auth/login',
            method: 'POST',
            data: { code: loginRes.code },
            skipAuth: true,
          });

          app.globalData.token = res.access_token;
          app.globalData.refreshToken = res.refresh_token;
          wx.setStorageSync('access_token', res.access_token);
          wx.setStorageSync('refresh_token', res.refresh_token);

          // Fetch user info
          await app.fetchUserInfo();
          resolve(app.globalData.userInfo);
        } catch (e) {
          reject(e);
        }
      },
      fail: reject,
    });
  });
}

/**
 * Get user profile from WeChat (nickname, avatar).
 * Use <button open-type="chooseAvatar"> for avatar
 * and <input type="nickname"> for nickname in UI.
 */
function getWechatUserProfile() {
  return new Promise((resolve, reject) => {
    wx.getUserProfile({
      desc: '用于完善用户资料',
      success: (res) => resolve(res.userInfo),
      fail: reject,
    });
  });
}

/**
 * Get phone number from WeChat.
 * Use <button open-type="getPhoneNumber"> in UI.
 */
function getPhoneNumber(e) {
  const { code } = e.detail;
  if (!code) return Promise.reject('No code');
  return app.request({
    url: '/auth/phone',
    method: 'POST',
    data: { code },
  });
}

/**
 * Check login status, redirect if not logged in.
 */
function checkLogin() {
  if (!app.globalData.token) {
    wx.reLaunch({ url: '/pages/common/login' });
    return false;
  }
  return true;
}

module.exports = { login, getWechatUserProfile, getPhoneNumber, checkLogin };
