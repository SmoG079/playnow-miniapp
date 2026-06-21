const app = getApp();
const wxpay = require('../../utils/wxpay');

Page({
  data: {
    tournamentId: null,
    tournament: null,
    loading: true,
    myRegistration: null,
    isLoggedIn: false,
    isFull: false,
    processing: false,
  },

  onLoad(options) {
    const id = options.id;
    if (!id) {
      wx.showToast({ title: '参数错误', icon: 'none' });
      return wx.navigateBack();
    }
    this.setData({ tournamentId: id, isLoggedIn: !!app.globalData.token });
    this.loadTournament();
  },

  onBack() {
    wx.navigateBack();
  },

  onShow() {
    if (this.data.tournamentId) {
      this.setData({ isLoggedIn: !!app.globalData.token });
      this.loadTournament();
    }
  },

  async loadTournament() {
    this.setData({ loading: true });
    try {
      const tournament = await app.request({ url: `/tournaments/${this.data.tournamentId}` });
      const currentUserId = app.globalData.userInfo && app.globalData.userInfo.id;
      const myRegistration = (tournament.registrations || []).find(
        r => r.user_id === currentUserId
      );
      const isFull = tournament.max_participants &&
        tournament.current_participants >= tournament.max_participants;

      const btnState = this.computeButtonState(tournament, myRegistration, isFull);

      this.setData({
        tournament,
        myRegistration,
        isFull,
        loading: false,
        btnText: btnState.text,
        btnClass: btnState.className,
      });
    } catch (e) {
      console.error(e);
      wx.showToast({ title: '加载失败', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  computeButtonState(tournament, myRegistration, isFull) {
    if (!this.data.isLoggedIn) {
      return { text: '登录后报名', className: '' };
    }
    if (tournament.status !== 'open') {
      return { text: '报名未开始', className: 'disabled' };
    }
    if (myRegistration) {
      if (myRegistration.status === 'registered') {
        return { text: '去支付', className: 'pay' };
      }
      if (myRegistration.status === 'confirmed') {
        return { text: '已报名', className: 'disabled' };
      }
      return { text: '已报名', className: 'disabled' };
    }
    if (isFull) {
      return { text: '已满员', className: 'disabled' };
    }
    const fee = tournament.entry_fee || 0;
    if (fee > 0) {
      return { text: `报名 ¥${fee}`, className: 'pay' };
    }
    return { text: '立即报名', className: '' };
  },

  onRegister() {
    if (!this.data.isLoggedIn) {
      return wx.navigateTo({ url: '/pages/common/login' });
    }
    if (this.data.myRegistration) {
      const status = this.data.myRegistration.status;
      if (status === 'registered') {
        // Need to pay
        return this.onPay();
      }
      return wx.showToast({ title: '您已报名', icon: 'none' });
    }

    const tournament = this.data.tournament;
    const fee = tournament.entry_fee || 0;
    const content = fee > 0
      ? `确定报名「${tournament.title}」吗？报名费 ¥${fee}`
      : `确定报名「${tournament.title}」吗？`;

    wx.showModal({
      title: '确认报名',
      content,
      success: (res) => {
        if (res.confirm) this.doRegister();
      },
    });
  },

  async doRegister() {
    if (this.data.processing) return;
    this.setData({ processing: true });
    try {
      const res = await app.request({
        url: `/tournaments/${this.data.tournamentId}/register`,
        method: 'POST',
      });
      if (res.order) {
        await wxpay.payOrder(res.order.id);
        wx.showToast({ title: '报名成功', icon: 'success' });
      } else {
        wx.showToast({ title: '报名成功', icon: 'success' });
      }
      this.loadTournament();
    } catch (e) {
      console.error(e);
      const msg = (e.data && e.data.detail) || '报名失败';
      wx.showToast({ title: msg, icon: 'none' });
    } finally {
      this.setData({ processing: false });
    }
  },

  async onPay() {
    if (!this.data.myRegistration) return;
    if (this.data.processing) return;
    this.setData({ processing: true });
    try {
      await wxpay.payTournament(this.data.tournamentId);
      wx.showToast({ title: '支付成功', icon: 'success' });
      this.loadTournament();
    } catch (e) {
      if (e.message !== '用户取消支付') {
        wx.showToast({ title: '支付失败', icon: 'none' });
      }
    } finally {
      this.setData({ processing: false });
    }
  },

  onCallPhone() {
    const phone = this.data.tournament && this.data.tournament.contact_phone;
    if (phone) {
      wx.makePhoneCall({ phoneNumber: phone });
    } else {
      wx.showToast({ title: '暂无电话', icon: 'none' });
    }
  },

  onPullDownRefresh() {
    this.loadTournament().then(() => wx.stopPullDownRefresh());
  },

  onShareAppMessage() {
    const tournament = this.data.tournament;
    return {
      title: tournament ? tournament.title : '赛事详情',
      path: `/pages/common/tournament-detail?id=${this.data.tournamentId}`,
    };
  },
});
