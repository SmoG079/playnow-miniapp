const app = getApp();

/**
 * Permission check utility.
 * Frontend gate for UI visibility. Backend enforces final auth.
 */

/** User has logged in */
function isLoggedIn() {
  return !!app.globalData.token;
}

/** User is a club admin (or platform admin) */
function isClubAdmin() {
  return app.isClubAdmin();
}

/** User manages a specific club */
function canManageClub(clubId) {
  return app.globalData.managedClubIds.includes(clubId);
}

/** User is platform super admin */
function isPlatformAdmin() {
  return app.globalData.role === 'platform_admin';
}

/** Get current user role */
function getRole() {
  return app.globalData.role;
}

/** Get managed club IDs */
function getManagedClubIds() {
  return app.globalData.managedClubIds || [];
}

/** Guard: redirect to login if not authenticated */
function requireLogin() {
  if (!isLoggedIn()) {
    wx.reLaunch({ url: '/pages/common/login' });
    return false;
  }
  return true;
}

/** Guard: show toast and return false if user is not a club admin */
function requireClubAdmin() {
  if (!requireLogin()) return false;
  if (!isClubAdmin()) {
    wx.showToast({ title: '需要俱乐部管理员权限', icon: 'none' });
    return false;
  }
  return true;
}

module.exports = {
  isLoggedIn,
  isClubAdmin,
  canManageClub,
  isPlatformAdmin,
  getRole,
  getManagedClubIds,
  requireLogin,
  requireClubAdmin,
};
