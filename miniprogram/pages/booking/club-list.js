const app = getApp();

Page({
  data: {
    clubs: [],
    loading: false,
    page: 1,
    hasMore: true,
    keyword: '',
    sportFilter: '',
    latitude: null,
    longitude: null,
    sortBy: 'default',
  },

  onLoad() {
    this.getLocation();
    this.loadClubs();
  },

  onToggleSort() {
    const next = this.data.sortBy === 'distance' ? 'default' : 'distance';
    this.setData({ sortBy: next });
    this.loadClubs();
  },

  onShow() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 1 });
    }
  },

  onPullDownRefresh() {
    this.resetAndLoadClubs().then(
      () => wx.stopPullDownRefresh(),
      () => wx.stopPullDownRefresh()
    );
  },

  onReachBottom() {
    if (this.data.hasMore && !this.data.loading) {
      this.loadClubs(true);
    }
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

  async loadClubs(append = false) {
    this.setData({ loading: true });
    try {
      const page = append ? this.data.page + 1 : 1;
      let url = `/clubs?page=${page}&page_size=20`;
      if (this.data.latitude && this.data.sortBy === 'distance') {
        url += `&lat=${this.data.latitude}&lng=${this.data.longitude}&sort_by=distance`;
      }
      if (this.data.sportFilter) {
        url += `&sport=${this.data.sportFilter}`;
      }
      if (this.data.keyword) {
        url += `&keyword=${encodeURIComponent(this.data.keyword)}`;
      }
      const res = await app.request({ url });
      const items = res.items || [];
      const clubs = append ? this.data.clubs.concat(items) : items;
      this.setData({
        clubs,
        page,
        hasMore: items.length === 20,
      });
    } catch (e) {
      console.error('Load clubs failed', e);
    } finally {
      this.setData({ loading: false });
    }
  },

  resetAndLoadClubs() {
    this.setData({ page: 1, hasMore: true, clubs: [] }, () => {
      this.loadClubs();
    });
  },

  onSearchInput(e) {
    this.setData({ keyword: e.detail.value });
  },

  onSearch() {
    this.resetAndLoadClubs();
  },

  onSportFilter(e) {
    const val = e.currentTarget.dataset.value;
    this.setData({ sportFilter: val });
    this.resetAndLoadClubs();
  },

  onSortToggle() {
    if (this.data.sortBy === 'distance') {
      this.setData({ sortBy: 'default' }, () => this.resetAndLoadClubs());
      return;
    }
    if (this.data.latitude) {
      this.setData({ sortBy: 'distance' }, () => this.resetAndLoadClubs());
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
    // venue-detail is the club booking page: it loads club info + venue slots
    wx.navigateTo({ url: `/pages/booking/venue-detail?id=${id}` });
  },

  onShareAppMessage() {
    return {
      title: '发现身边的运动俱乐部',
      path: '/pages/booking/club-list',
    };
  },
});
