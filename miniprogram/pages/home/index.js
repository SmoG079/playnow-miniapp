const app = getApp();

Page({
  data: {
    posts: [],
    loading: false,
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
      const sortBy = this.data.sortBy;

      let postUrl = '/posts?page=1&page_size=10';
      if (sortBy === 'distance' && loc) {
        postUrl += `&sort_by=distance&lat=${loc.latitude}&lng=${loc.longitude}`;
      }

      const postRes = await app.request({ url: postUrl });
      const posts = (postRes.items || []).map(item => ({
        ...item,
        is_full: item.registration_count >= item.players_needed,
        is_registered: item.is_registered || false,
        weekday: this.getWeekday(item.preferred_date),
      }));

      this.setData({ posts });
    } catch (e) {
      console.error('Load feed failed', e);
    } finally {
      this.setData({ loading: false });
    }
  },

  getWeekday(dateStr) {
    if (!dateStr) return '';
    const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    const d = new Date(dateStr);
    return days[d.getDay()];
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

  onFilterSort() {
    const items = ['最新发布', '距离最近', '热度最高'];
    wx.showActionSheet({
      itemList: items,
      success: (res) => {
        const sortMap = ['created', 'distance', 'hot'];
        const sortBy = sortMap[res.tapIndex];
        if (sortBy === 'distance' && !this.data.hasLocation) {
          wx.showModal({
            title: '需要位置权限',
            content: '按距离排序需要获取您的位置',
            success: (r) => {
              if (r.confirm) {
                this.initLocation().then(() => {
                  if (this.data.hasLocation) {
                    this.setData({ sortBy });
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
      }
    });
  },

  onFilterTime() {
    wx.showActionSheet({
      itemList: ['全部时间', '今天', '明天', '本周', '本周末'],
      success: (res) => {
        // TODO: implement time filter
        console.log('Time filter:', res.tapIndex);
      }
    });
  },

  onFilterLevel() {
    wx.showActionSheet({
      itemList: ['全部等级', '2.0以下', '2.5', '3.0', '3.5', '4.0', '4.5', '5.0+'],
      success: (res) => {
        // TODO: implement level filter
        console.log('Level filter:', res.tapIndex);
      }
    });
  },

  onFilterMore() {
    wx.showToast({ title: '高级筛选开发中', icon: 'none' });
  },

  onPostDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/common/post-detail?id=${id}` });
  },

  onActionTap(e) {
    e.stopPropagation();
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/common/post-detail?id=${id}` });
  },

  onSearch() {
    wx.navigateTo({ url: '/pages/home/search' });
  },

  onCityTap() {
    wx.showToast({ title: '城市切换开发中', icon: 'none' });
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
      title: '运动俱乐部 - 发现你的运动圈',
      path: '/pages/home/index',
    };
  },
});
