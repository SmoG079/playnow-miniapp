// Calendar filter TODO
const app = getApp();

const SORT_OPTIONS = [
  { label: '最新发布', value: 'created' },
  { label: '距离最近', value: 'distance' },
];

const NTRP_LEVELS = ['1.0', '1.5', '2.0', '2.5', '3.0', '3.5', '4.0', '4.5', '5.0', '5.5', '6.0', '6.5', '7.0'];

const DISTANCE_OPTIONS = [
  { label: '全部距离', value: 'all' },
  { label: '1km内', value: '1' },
  { label: '3km内', value: '3' },
  { label: '5km内', value: '5' },
  { label: '10km内', value: '10' },
  { label: '20km内', value: '20' },
  { label: '50km内', value: '50' },
];

function generateCalendar() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const months = [];
  for (let i = 0; i < 2; i++) {
    const base = new Date(today.getFullYear(), today.getMonth() + i, 1);
    const year = base.getFullYear();
    const month = base.getMonth();
    const monthStr = `${year}年${String(month + 1).padStart(2, '0')}月`;
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const weeks = [];
    let currentWeek = new Array(firstDay).fill(null);
    for (let day = 1; day <= daysInMonth; day++) {
      const date = new Date(year, month, day);
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const dayOfWeek = date.getDay();
      const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
      const isPast = date.getTime() < today.getTime();
      currentWeek.push({ day, dateStr, isWeekend, isPast });
      if (currentWeek.length === 7) {
        weeks.push(currentWeek);
        currentWeek = [];
      }
    }
    if (currentWeek.length > 0) {
      while (currentWeek.length < 7) currentWeek.push(null);
      weeks.push(currentWeek);
    }
    months.push({ title: monthStr, weeks });
  }
  return months;
}

function formatDateLabel(dateStr) {
  if (!dateStr) return '';
  const parts = dateStr.split('-');
  if (parts.length !== 3) return '';
  return `${parts[1]}.${parts[2]}`;
}

Page({
  data: {
    posts: [],
    loading: false,
    sortBy: 'created',  // 'created' | 'distance'
    hasLocation: false,
    locationError: false,
    sportType: '网球',

    // Filter popup
    showFilterPopup: false,
    filterSort: 'created',
    filterDate: '',
    filterDateLabel: '',
    filterLevels: [],
    filterDistance: 'all',
    activeFilterCount: 0,
    showCalendarPopup: false,
    calendarMonths: [],
    selectedCalendarDate: '',

    // Constants for wxml
    SORT_OPTIONS,
    WEEKDAYS: ['日', '一', '二', '三', '四', '五', '六'],
    NTRP_LEVELS,
    DISTANCE_OPTIONS,
  },

  onLoad() {
    this.initLocation().then(() => this.loadFeed());
  },

  onShow() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 0 });
    }
    if (app.globalData.needRefreshFeed) {
      app.globalData.needRefreshFeed = false;
      this.loadFeed();
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
      const { sortBy, filterDate, filterLevels, filterDistance } = this.data;

      let postUrl = '/posts?page=1&page_size=10';
      postUrl += `&sport=${encodeURIComponent(this.data.sportType)}`;
      if (sortBy === 'distance' && loc) {
        postUrl += `&sort_by=distance&lat=${loc.latitude}&lng=${loc.longitude}`;
      }
      if (filterDate) {
        postUrl += `&date=${filterDate}`;
      }
      if (filterLevels && filterLevels.length > 0) {
        postUrl += `&ntrp_levels=${filterLevels.join(',')}`;
      }
      if (filterDistance && filterDistance !== 'all' && loc) {
        postUrl += `&max_distance=${filterDistance}`;
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
    const { filterDate } = this.data;
    const calendarMonths = this.generateCalendarData();
    
    // Restore selected state if filterDate exists
    if (filterDate) {
      calendarMonths.forEach(month => {
        month.days.forEach(day => {
          if (day.fullDate === filterDate) {
            day.isSelected = true;
          }
        });
      });
    }
    
    this.setData({
      showCalendarPopup: true,
      showFilterPopup: false,
      calendarMonths,
      selectedCalendarDate: filterDate || '',
    });
  },

  onFilterLevel() {
    const items = ['全部等级', ...NTRP_LEVELS];
    wx.showActionSheet({
      itemList: items,
      success: (res) => {
        const tapIndex = res.tapIndex;
        if (tapIndex === 0) {
          this.setData({ filterLevels: [] });
        } else {
          const level = NTRP_LEVELS[tapIndex - 1];
          this.setData({ filterLevels: [level] });
        }
        this.loadFeed();
      }
    });
  },

  generateCalendarData() {
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    const months = [];
    const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];
    
    for (let i = 0; i < 2; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
      const year = d.getFullYear();
      const month = d.getMonth() + 1; // 1-12
      const daysInMonth = new Date(year, month, 0).getDate();
      const firstDayOfWeek = new Date(year, month - 1, 1).getDay(); // 0=Sunday
      
      const days = [];
      // Pad empty cells before the first day
      for (let p = 0; p < firstDayOfWeek; p++) {
        days.push({ date: 0, isPadding: true });
      }
      
      for (let d = 1; d <= daysInMonth; d++) {
        const dateObj = new Date(year, month - 1, d);
        const dayOfWeek = dateObj.getDay();
        const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
        const isToday = dateObj.getTime() === now.getTime();
        const isPast = dateObj.getTime() < now.getTime();
        
        days.push({
          date: d,
          fullDate: `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`,
          dayOfWeek,
          isWeekend,
          isToday,
          isPast,
          isSelected: false,
        });
      }
      
      months.push({ year, month, days, WEEKDAYS });
    }
    return months;
  },

  onFilterMore() {
    this.setData({
      showFilterPopup: true,
      filterSort: this.data.sortBy || 'created',
      filterDate: this.data.filterDate || '',
      filterLevels: this.data.filterLevels || [],
      filterDistance: this.data.filterDistance || 'all',
      calendarMonths: this.generateCalendarData(),
    });
  },

  onCloseCalendarPopup() {
    this.setData({ showCalendarPopup: false });
  },

  onCalendarPanelTap() {
    // prevent bubbling
  },

  onCalendarDaySelect(e) {
    const { date, ispast } = e.currentTarget.dataset;
    if (ispast === 'true' || ispast === true) return;
    
    const months = this.data.calendarMonths.map(month => ({
      ...month,
      days: month.days.map(day => ({
        ...day,
        isSelected: day.fullDate === date && !day.isPadding,
      })),
    }));
    
    this.setData({
      calendarMonths: months,
      selectedCalendarDate: date,
    });
  },

  onCalendarReset() {
    const months = this.data.calendarMonths.map(month => ({
      ...month,
      days: month.days.map(day => ({
        ...day,
        isSelected: false,
      })),
    }));
    this.setData({
      calendarMonths: months,
      selectedCalendarDate: '',
    });
  },

  onCalendarConfirm() {
    const { selectedCalendarDate } = this.data;
    this.setData({
      showCalendarPopup: false,
      filterDate: selectedCalendarDate,
      filterDateLabel: formatDateLabel(selectedCalendarDate),
    }, () => {
      this.loadFeed();
    });
  },

  onCloseFilterPopup() {
    this.setData({ showFilterPopup: false });
  },

  onPanelTap() {
    // prevent bubbling to overlay
  },

  onFilterSortChange(e) {
    const value = e.currentTarget.dataset.value;
    if (value === 'distance' && !this.data.hasLocation) {
      wx.showModal({
        title: '需要位置权限',
        content: '按距离排序需要获取您的位置',
        success: (res) => {
          if (res.confirm) {
            this.initLocation().then(() => {
              if (this.data.hasLocation) {
                this.setData({ filterSort: 'distance' });
              }
            });
          }
        }
      });
      return;
    }
    this.setData({ filterSort: value });
  },

  onFilterDateChange(e) {
    const { date, past } = e.currentTarget.dataset;
    if (!date || past) return;
    this.setData({ filterDate: date });
  },

  onFilterLevelChange(e) {
    const value = e.currentTarget.dataset.value;
    const levels = [...this.data.filterLevels];
    const idx = levels.indexOf(value);
    if (idx > -1) {
      levels.splice(idx, 1);
    } else {
      levels.push(value);
    }
    this.setData({ filterLevels: levels });
  },

  onFilterDistanceChange(e) {
    const value = e.currentTarget.dataset.value;
    if (value !== 'all' && !this.data.hasLocation) {
      wx.showModal({
        title: '需要位置权限',
        content: '按距离筛选需要获取您的位置',
        success: (res) => {
          if (res.confirm) {
            this.initLocation().then(() => {
              if (this.data.hasLocation) {
                this.setData({ filterDistance: value });
              }
            });
          }
        }
      });
      return;
    }
    this.setData({ filterDistance: value });
  },

  computeActiveFilterCount() {
    const { filterDate, filterLevels, filterDistance } = this.data;
    let count = 0;
    if (filterDate) count++;
    if (filterLevels && filterLevels.length > 0) count++;
    if (filterDistance && filterDistance !== 'all') count++;
    return count;
  },

  onResetFilters() {
    this.setData({
      filterSort: 'created',
      filterDate: '',
      filterDateLabel: '',
      filterLevels: [],
      filterDistance: 'all',
    });
  },

  onConfirmFilters() {
    const activeFilterCount = this.computeActiveFilterCount();
    const { filterSort, filterDate, filterLevels } = this.data;
    this.setData({
      showFilterPopup: false,
      sortBy: filterSort,
      filterDate,
      filterDateLabel: formatDateLabel(filterDate),
      filterLevels,
      activeFilterCount,
    }, () => {
      this.loadFeed();
    });
  },

  onPostDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/common/post-detail?id=${id}` });
  },

  onActionTap(e) {
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
