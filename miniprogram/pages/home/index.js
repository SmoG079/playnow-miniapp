const app = getApp();

const NTRP_OPTIONS = ['不限', '1.0', '1.5', '2.0', '2.5', '3.0', '3.5', '4.0', '4.5', '5.0', '5.5', '6.0', '6.5', '7.0'];

Page({
  data: {
    activeTab: 0,
    matchFilter: 'all',
    filterDate: '',
    filterNtrp: '',
    sortByDist: false,
    lat: null,
    lng: null,
    posts: [],
    displayPosts: [],
    tournaments: [],
    displayTournaments: [],
    loading: false,
    NTRP_OPTIONS,
  },

  onLoad() {
    this.getLocation();
    this.loadFeed();
  },

  onShow() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 0 });
    }
    this.loadFeed();
  },

  onPullDownRefresh() {
    this.loadFeed().then(() => wx.stopPullDownRefresh());
  },

  getLocation() {
    wx.getLocation({ type: 'gcj02', success: r => {
      this.setData({ lat: r.latitude, lng: r.longitude });
      if (this.data.sortByDist) this.loadFeed();
    }, fail: () => this.setData({ sortByDist: false }) });
  },

  async loadFeed() {
    const requestId = this._requestId = (this._requestId || 0) + 1;
    this.setData({ loading: true });
    try {
      let postUrl = '/posts?page=1&page_size=20';
      let tourUrl = '/tournaments?status=open&page=1&page_size=10';
      if (this.data.sortByDist && this.data.lat) {
        postUrl += `&sort_by=distance&lat=${this.data.lat}&lng=${this.data.lng}`;
        tourUrl += `&sort_by=distance&lat=${this.data.lat}&lng=${this.data.lng}`;
      }
      if (this.data.filterNtrp) {
        postUrl += `&ntrp_levels=${this.data.filterNtrp}`;
      }
      const [postRes, tourRes] = await Promise.all([
        app.request({ url: postUrl }),
        app.request({ url: tourUrl }),
      ]);
      if (requestId !== this._requestId) return;
      this.setData({ posts: postRes.items || [], tournaments: tourRes.items || [] });
      this._doFilter();
    } catch (e) {
      console.error('Load feed failed', e);
    } finally {
      if (requestId === this._requestId) this.setData({ loading: false });
    }
  },

  _doFilter() {
    let arr = this.data.posts;
    if (this.data.matchFilter === 'free') arr = arr.filter(p => !p.venue_id);
    else if (this.data.matchFilter === 'venue') arr = arr.filter(p => !!p.venue_id);
    if (this.data.filterDate) arr = arr.filter(p => p.preferred_date === this.data.filterDate);
    this.setData({ displayPosts: arr, displayTournaments: this.data.tournaments });
  },

  onMatchFilter(e) { this.setData({ matchFilter: e.currentTarget.dataset.filter }, () => this._doFilter()); },
  onDateChange(e) { this.setData({ filterDate: e.detail.value }, () => this._doFilter()); },
  onClearDate() { this.setData({ filterDate: '' }, () => this._doFilter()); },
  onToggleDist() {
    this.setData({ sortByDist: !this.data.sortByDist }, () => this.loadFeed());
  },
  onNtrpChange(e) {
    this.setData({ filterNtrp: e.currentTarget.dataset.val }, () => this.loadFeed());
  },

  onTabChange(e) { this.setData({ activeTab: parseInt(e.currentTarget.dataset.tab) }); },
  onPostDetail(e) { wx.navigateTo({ url: '/pages/common/post-detail?id=' + e.currentTarget.dataset.id }); },
  onTourDetail(e) { wx.navigateTo({ url: '/pages/common/tournament-detail?id=' + e.currentTarget.dataset.id }); },
  onShareAppMessage(res) {
    if (res.from === 'button') {
      const d = res.target.dataset;
      return { title: d.title || '来运动吧！', path: '/pages/common/post-detail?id=' + d.id };
    }
    return { title: '网球俱乐部', path: '/pages/home/index' };
  },
});
