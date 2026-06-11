const app = getApp();

Page({
  data: {
    posts: [],
    tournaments: [],
    loading: false,
    sportFilter: '',
    sportFilters: ['全部', '羽毛球', '篮球', '网球', '乒乓球', '足球'],
    activeSport: '全部',
    sortBy: 'created',  // 'created' | 'distance'
    hasLocation: false,
    locationError: false,
  },

  onLoad() {
    this.initLocation().then(() => this.loadFeed());
  },

  onShow() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 0 });
    }
  },

  onPullDownRefresh() {
    this.loadFeed().then(() => wx.stopPullDownRefresh());
  },

  async initLocation() {
    try {
      await app.getUserLocation();
      this.setData({ hasLocation: true, locationError: false });
    } catch (e) {
      console.error('Location init failed', e);
      this.setData({ hasLocation: false, locationError: true });
    }
  },

  async loadFeed() {
    this.setData({ loading: true });
    try {
      const loc = app.globalData.userLocation;
      const sport = this.data.activeSport === '全部' ? '' : this.data.activeSport;
      const sortBy = this.data.sortBy;

      let postUrl = '/posts?page=1&page_size=10';
      if (sport) postUrl += `&sport=${sport}`;
      if (sortBy === 'distance' && loc) {
        postUrl += `&sort_by=distance&lat=${loc.latitude}&lng=${loc.longitude}`;
      }

      const [postRes, tourRes] = await Promise.all([
        app.request({ url: postUrl }),
        app.request({ url: '/tournaments?status=open&page=1&page_size=5' }),
      ]);

      this.setData({
        posts: postRes.items || [],
        tournaments: tourRes.items || [],
      });
    } catch (e) {
      console.error('Load feed failed', e);
    } finally {
      this.setData({ loading: false });
    }
  },

  onSortChange(e) {
    const sortBy = e.currentTarget.dataset.sort;
    if (sortBy === 'distance' && !this.data.hasLocation) {
      wx.showModal({
        title: '需要位置权限',
        content: '按距离排序需要获取您的位置',
        success: (res) => {
          if (res.confirm) {
            this.initLocation().then(() => {
              if (this.data.hasLocation) {
                this.setData({ sortBy: 'distance' });
                this.loadFeed();
              }
            });
          }
        }
      });
      return;
    }
    this.setData({ sortBy });
    this.loadFeed();
  },

  onSportFilter(e) {
    const sport = e.currentTarget.dataset.sport;
    this.setData({ activeSport: sport });
    this.loadFeed();
  },

  onPostDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/common/post-detail?id=${id}` });
  },

  onTourDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/common/tournament-detail?id=${id}` });
  },

  onShare() {
    // Called by share button in posts/tournaments
  },

  onShareAppMessage(res) {
    if (res.from === 'button') {
      const data = res.target.dataset;
      return {
        title: data.title || '来运动吧！',
        path: `/pages/common/post-detail?id=${data.id}`,
        imageUrl: data.image || '',
      };
    }
    return {
      title: '运动俱乐部 - 约球订场平台',
      path: '/pages/home/index',
    };
  },

  onSearch() {
    wx.navigateTo({ url: '/pages/home/search' });
  },
});
