const app = getApp();
const perm = require('../../utils/permission');

Page({
  data: {
    clubId: null,
    venues: [],
    loading: false,
    showModal: false,
    modalMode: 'create', // 'create' | 'edit'
    editingVenue: null,
    form: {
      name: '',
      sport_type: '',
      price_per_hour: '',
      max_capacity: 4,
      sort_order: 0,
      status: 'active',
    },
  },

  onLoad(options) {
    if (!perm.requireClubAdmin()) return;
    const clubId = options.club_id || perm.getManagedClubIds()[0];
    if (!clubId) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      return wx.navigateBack();
    }
    this.setData({ clubId: parseInt(clubId) });
    this.loadVenues();
  },

  async loadVenues() {
    this.setData({ loading: true });
    try {
      const res = await app.request({ url: `/clubs/${this.data.clubId}/venues` });
      this.setData({ venues: res || [], loading: false });
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  onShowModal(e) {
    const mode = e.currentTarget.dataset.mode || 'create';
    const venue = e.currentTarget.dataset.venue;
    if (mode === 'edit' && venue) {
      this.setData({
        showModal: true,
        modalMode: 'edit',
        editingVenue: venue,
        form: {
          name: venue.name,
          sport_type: venue.sport_type,
          price_per_hour: String(venue.price_per_hour),
          max_capacity: venue.max_capacity || 4,
          sort_order: venue.sort_order || 0,
          status: venue.status || 'active',
        },
      });
    } else {
      this.setData({
        showModal: true,
        modalMode: 'create',
        editingVenue: null,
        form: { name: '', sport_type: '', price_per_hour: '', max_capacity: 4, sort_order: 0, status: 'active' },
      });
    }
  },

  onCloseModal() {
    this.setData({ showModal: false });
  },

  onInputChange(e) {
    const { field } = e.currentTarget.dataset;
    const value = e.detail.value;
    this.setData({ [`form.${field}`]: value });
  },

  async onSubmit() {
    const { form, modalMode, editingVenue, clubId } = this.data;
    if (!form.name.trim()) {
      return wx.showToast({ title: '请输入场地名称', icon: 'none' });
    }
    if (!form.sport_type) {
      return wx.showToast({ title: '请选择运动类型', icon: 'none' });
    }
    const price = parseFloat(form.price_per_hour);
    if (isNaN(price) || price <= 0) {
      return wx.showToast({ title: '请输入有效的价格', icon: 'none' });
    }

    const payload = {
      name: form.name.trim(),
      sport_type: form.sport_type,
      price_per_hour: price,
      max_capacity: parseInt(form.max_capacity) || 4,
      sort_order: parseInt(form.sort_order) || 0,
      status: form.status,
    };

    try {
      if (modalMode === 'edit' && editingVenue) {
        await app.request({
          url: `/venues/${editingVenue.id}/with-club/${clubId}`,
          method: 'PUT',
          data: payload,
        });
        wx.showToast({ title: '更新成功', icon: 'success' });
      } else {
        await app.request({
          url: `/venues/with-club/${clubId}`,
          method: 'POST',
          data: payload,
        });
        wx.showToast({ title: '创建成功', icon: 'success' });
      }
      this.setData({ showModal: false });
      this.loadVenues();
    } catch (e) {
      wx.showToast({ title: '操作失败', icon: 'none' });
    }
  },

  onDelete(e) {
    const venue = e.currentTarget.dataset.venue;
    wx.showModal({
      title: '确认删除',
      content: `确定要删除场地"${venue.name}"吗？`,
      confirmColor: '#f44336',
      success: (res) => {
        if (res.confirm) this.doDelete(venue.id);
      },
    });
  },

  async doDelete(venueId) {
    try {
      await app.request({
        url: `/venues/${venueId}/with-club/${this.data.clubId}`,
        method: 'DELETE',
      });
      wx.showToast({ title: '已删除', icon: 'success' });
      this.loadVenues();
    } catch (e) {
      wx.showToast({ title: '删除失败', icon: 'none' });
    }
  },

  onSlotManage(e) {
    const venueId = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/publish/slot-manage?club_id=${this.data.clubId}&venue_id=${venueId}`,
    });
  },

  onPanelTap() {
    // Prevent modal close when tapping inside modal content
  },

  onPullDownRefresh() {
    this.loadVenues().then(() => wx.stopPullDownRefresh());
  },
});
