const app = getApp();

Page({
  data: {
    posts: [],
    tournaments: [],
    loading: false,
    sportFilter: '',
    sportFilters: ['全部', '羽毛球', '篮球', '网球', '乒乓球', '足球'],
    activeSport: '全部',
  },

  onLoad() {
    this.loadFeed();
  },

  onShow() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 0 });
    }
  },

  onPullDownRefresh() {
    this.loadFeed().then(() => wx.stopPullDownRefresh());
  },

  async loadFeed() {
    this.setData({ loading: true });
    try {
      // Load posts + tournaments in parallel
      const [postRes, tourRes] = await Promise.all([
        app.request({ url: '/posts?page=1&page_size=10' }),
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

  onSportFilter(e) {
    const sport = e.currentTarget.dataset.sport;
    if (sport === '全部') {
      this.loadFeed();
    } else {
      app.request({ url: `/posts?sport=${sport}&page=1` }).then(res => {
        this.setData({ posts: res.items || [] });
      });
    }
    this.setData({ activeSport: sport });
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

  // Share to WeChat group/chat
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
