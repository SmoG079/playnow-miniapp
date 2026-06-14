const app = getApp();

Page({
  data: {
    clubs: [],
    loading: false,
    keyword: '',
    sportFilter: '',
    latitude: null,
    longitude: null,
    sortBy: 'default', // 'default' | 'distance'
  },

  onLoad() {
    this.getLocation();
    this.loadClubs();
  },

  onShow() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 1 });
    }
  },

  onPullDownRefresh() {
    this.loadClubs().then(() => wx.stopPullDownRefresh());
  },

  getLocation() {
    wx.getLocation({
      type: 'gcj02',
      success: (res) => {
        this.setData({ latitude: res.latitude, longitude: res.longitude }, () => {
          if (this.data.sortBy === 'distance') {
            this.loadClubs();
          }
        });
      },
      fail: () => {
        // Location denied, still show clubs without distance
      },
    });
  },

  async loadClubs() {
    this.setData({ loading: true });
    try {
      let url = '/clubs?page=1&page_size=20';
      if (this.data.latitude && this.data.sortBy === 'distance') {
        url += `&lat=${this.data.latitude}&lng=${this.data.longitude}&sort_by=distance`;
      }
      if (this.data.sportFilter) {
        url += `&sport=${this.data.sportFilter}`;
      }
      if (this.data.keyword) {
        url += `&keyword=${this.data.keyword}`;
      }
      const res = await app.request({ url });
      this.setData({ clubs: res.items || [] });
    } catch (e) {
      console.error('Load clubs failed', e);
    } finally {
      this.setData({ loading: false });
    }
  },

  onSearchInput(e) {
    this.setData({ keyword: e.detail.value });
  },

  onSearch() {
    this.loadClubs();
  },

  onSportFilter(e) {
    const val = e.currentTarget.dataset.value;
    this.setData({ sportFilter: val });
    this.loadClubs();
  },

  onSortToggle() {
    if (this.data.sortBy === 'distance') {
      this.setData({ sortBy: 'default' }, () => this.loadClubs());
      return;
    }
    if (this.data.latitude) {
      this.setData({ sortBy: 'distance' }, () => this.loadClubs());
      return;
    }
    wx.showModal({
      title: '需要位置权限',
      content: '按距离排序需要获取您的位置',
      success: (res) => {
        if (res.confirm) {
          this.getLocation();
        }
      },
    });
  },

  onCreateClub() {
    wx.navigateTo({ url: '/pages/publish/club-create' });
  },

  onClubDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/booking/venue-detail?id=${id}` });
  },

  onShareAppMessage() {
    return {
      title: '发现身边的运动俱乐部',
      path: '/pages/booking/club-list',
    };
  },
});
