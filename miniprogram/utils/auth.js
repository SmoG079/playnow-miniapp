const app = getApp();

/**
 * WeChat login flow:
 * 1. wx.login() -> get code
 * 2. Backend exchanges code for JWT
 * 3. Store tokens in storage + globalData
 */
async function login() {
  const postLogin = async (code) => {
    const res = await app.request({
      url: '/auth/login',
      method: 'POST',
      data: { code },
      skipAuth: true,
    });
    app.globalData.token = res.access_token;
    app.globalData.refreshToken = res.refresh_token;
    wx.setStorageSync('access_token', res.access_token);
    wx.setStorageSync('refresh_token', res.refresh_token);
    await app.fetchUserInfo();
    return app.globalData.userInfo;
  };

  // Try real WeChat login first
  try {
    const code = await new Promise((resolve, reject) => {
      wx.login({ success: r => resolve(r.code), fail: reject });
    });
    if (code) return await postLogin(code);
  } catch (e) {
    app.clearSession();
    console.warn('wx.login failed:', e);
  }

  throw new Error('wx.login failed');
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

/**
 * Require phone number — redirect to edit profile if missing.
 * Returns true if phone exists, false if redirected.
 */
function requirePhone() {
  const phone = (app.globalData.userInfo || {}).phone;
  if (phone) return true;
  wx.showModal({
    title: '需要手机号',
    content: '预订场地和报名活动需要先提供手机号',
    confirmText: '去完善',
    success: (res) => {
      if (res.confirm) {
        wx.navigateTo({ url: '/pages/profile/edit' });
      }
    },
  });
  return false;
}

module.exports = { login, getPhoneNumber, checkLogin, requirePhone };
