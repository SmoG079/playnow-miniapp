const app = getApp();
const perm = require('../../utils/permission');

Page({
  data: {
    posts: [],
    tournaments: [],
    activeTab: 0,  // 0=约球帖, 1=比赛
    isAdmin: false,
    loading: false,
    showEditModal: false,
    editingId: null,
    editForm: {},
  },

  onEditPost(e) {
    const ds = e.currentTarget.dataset;
    this.setData({
      showEditModal: true, editingId: ds.id,
      editForm: {
        title: ds.title || '',
        preferred_date: ds.date || '',
        preferred_start: ds.start || '',
        preferred_end: ds.end || '',
        players_needed: ds.needed || '1',
        price: ds.price || '0',
        level_required: ds.level || '',
        notes: ds.notes || '',
      },
    });
  },
  onCloseEditModal() { this.setData({ showEditModal: false }); },
  onEditField(e) {
    this.setData({ ['editForm.' + e.currentTarget.dataset.field]: e.detail.value });
  },
  async onSaveEdit() {
    if (this._saving) return;
    const f = this.data.editForm;
    if (!String(f.title || '').trim() || !f.preferred_date || !f.preferred_start || !f.preferred_end || f.preferred_end <= f.preferred_start) return wx.showToast({ title: '请检查标题与活动时间', icon: 'none' });
    if (!Number.isInteger(Number(f.players_needed)) || Number(f.players_needed) < 1 || !Number.isFinite(Number(f.price)) || Number(f.price) < 0) return wx.showToast({ title: '请检查人数和费用', icon: 'none' });
    this._saving = true;
    try {
    await app.request({
      url: `/posts/${this.data.editingId}`, method: 'PUT',
      data: {
        title: f.title,
        preferred_date: f.preferred_date || null,
        preferred_start: f.preferred_start || null,
        preferred_end: f.preferred_end || null,
        players_needed: parseInt(f.players_needed) || 1,
        price: parseFloat(f.price) || 0,
        level_required: f.level_required || null,
        notes: f.notes || null,
      },
    });
    wx.showToast({ title: '已更新', icon: 'success' });
    this.setData({ showEditModal: false });
    this.loadData();
    } catch (e) {
      wx.showToast({ title: '保存失败，请重试', icon: 'none' });
    } finally { this._saving = false; }
  },

  onShow() {
    if (!perm.requireLogin()) return;
    this.setData({ isAdmin: perm.isClubAdmin() });
    this.loadData();
  },

  async loadData() {
    this.setData({ loading: true });
    try {
      const managedIds = perm.getManagedClubIds();
      const posts = await app.listAll('/users/me/posts');
      const tournaments = [];
      if (perm.isClubAdmin()) {
        for (const id of managedIds) tournaments.push(...await app.listAll(`/tournaments?club_id=${id}`));
      }
      this.setData({
        posts,
        tournaments,
      });
    } catch (e) {
      console.error('Load activity failed', e);
    } finally {
      this.setData({ loading: false });
    }
  },

  onTabChange(e) {
    this.setData({ activeTab: parseInt(e.currentTarget.dataset.tab) });
  },

  onPostDetail(e) {
    wx.navigateTo({ url: '/pages/common/post-detail?id=' + e.currentTarget.dataset.id });
  },

  onClosePost(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: '关闭活动',
      content: '确定关闭此约球帖吗？关闭后不再接受报名。',
      success: async (res) => {
        if (res.confirm) {
          try {
            await app.request({ url: `/posts/${id}`, method: 'DELETE' });
            wx.showToast({ title: '已关闭', icon: 'success' });
            this.loadData();
          } catch (e) { wx.showToast({ title: '操作失败', icon: 'none' }); }
        }
      },
    });
  },

  onTourDetail(e) {
    wx.navigateTo({ url: '/pages/common/tournament-detail?id=' + e.currentTarget.dataset.id });
  },
});
