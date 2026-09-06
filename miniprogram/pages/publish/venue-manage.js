const app = getApp();
const perm = require('../../utils/permission');

Page({
  data: {
    clubId: null,
    venue: null,
    isEdit: false,
    form: { name: '', price_per_hour: '', price_rules: [] },
    loading: false,
    statusBarH: 0,
  },

  onLoad(options) {
    if (!perm.requireClubAdmin()) return;
    const barH = wx.getSystemInfoSync().statusBarHeight || 20;
    this.setData({ clubId: parseInt(options.club_id), statusBarH: barH });
    if (options.venue_id) {
      this.setData({ isEdit: true });
      this.loadVenue(parseInt(options.venue_id));
    }
  },

  onBack() { wx.navigateBack(); },

  async loadVenue(id) {
    try {
      const res = await app.request({ url: `/clubs/${this.data.clubId}/venues` });
      const v = (res || []).find(x => x.id === id);
      if (v) {
        this.setData({
          venue: v,
          form: { name: v.name, price_per_hour: String(v.price_per_hour || ''), price_rules: v.price_rules || [] },
        });
      }
    } catch (e) { console.error(e); }
  },

  onField(e) { this.setData({ ['form.' + e.currentTarget.dataset.field]: e.detail.value }); },

  // Price rules
  onAddRule() {
    const rules = [...this.data.form.price_rules, { type: 'date_range', start_date: '', end_date: '', start_time: '', end_time: '', price: '' }];
    this.setData({ 'form.price_rules': rules });
  },
  onRuleField(e) {
    const { idx, field } = e.currentTarget.dataset;
    const val = e.detail.value;
    const rules = [...this.data.form.price_rules];
    rules[idx][field] = val;
    this.setData({ 'form.price_rules': rules });
  },
  onRuleTypeChange(e) {
    const { idx } = e.currentTarget.dataset;
    const rules = [...this.data.form.price_rules];
    rules[idx].type = Number(e.detail.value) === 0 ? 'date_range' : 'daily_time';
    this.setData({ 'form.price_rules': rules });
  },
  onRemoveRule(e) {
    const idx = e.currentTarget.dataset.idx;
    const rules = this.data.form.price_rules.filter((_, i) => i !== idx);
    this.setData({ 'form.price_rules': rules });
  },

  async onSubmit() {
    if (this.data.loading) return;
    const f = this.data.form;
    if (!f.name) return wx.showToast({ title: '请输入场地名称', icon: 'none' });
    const price = parseFloat(f.price_per_hour);
    if (!price || price <= 0) return wx.showToast({ title: '请输入有效价格', icon: 'none' });
    for (const rule of f.price_rules || []) {
      if (!(Number(rule.price) > 0)) return wx.showToast({ title: '请填写有效规则价格', icon: 'none' });
      if (rule.type === 'date_range' && (!rule.start_date || !rule.end_date || rule.end_date < rule.start_date)) return wx.showToast({ title: '请检查规则日期范围', icon: 'none' });
      if ((rule.type === 'daily_time' || rule.start_time || rule.end_time) && (!rule.start_time || !rule.end_time || rule.end_time <= rule.start_time)) return wx.showToast({ title: '请检查规则时间范围', icon: 'none' });
    }
    const payload = {
      name: f.name, price_per_hour: price,
      price_rules: (f.price_rules || []).filter(r => r.price && parseFloat(r.price) > 0),
    };
    this.setData({ loading: true });
    try {
      if (this.data.isEdit && this.data.venue) {
        await app.request({ url: `/venues/${this.data.venue.id}/with-club/${this.data.clubId}`, method: 'PUT', data: payload });
      } else {
        await app.request({ url: `/venues/with-club/${this.data.clubId}`, method: 'POST', data: payload });
      }
      wx.showToast({ title: '保存成功', icon: 'success' });
      setTimeout(() => wx.navigateBack(), 1000);
    } catch (e) { wx.showToast({ title: '操作失败', icon: 'none' }); }
    finally { this.setData({ loading: false }); }
  },
});
