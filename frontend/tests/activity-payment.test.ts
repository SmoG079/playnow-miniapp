import { describe, it, expect } from 'vitest';
import { paymentLabel, registrationNotice } from '../src/domain/activity-payment';
describe('activity fee confirmation', () => {
  it('states the exact fee and organizer collection for offline registration', () => {
    const text = registrationNotice('35.5', 'offline');
    expect(text).toContain('¥35.50/人');
    expect(text).toContain('报名时无需线上支付');
    expect(text).toContain('组织者自行组织收款');
    expect(paymentLabel(35.5, 'offline')).toBe('线下付款');
  });
  it('requires WeChat payment only for online paid events', () => {
    expect(registrationNotice(10, 'online')).toContain('线上完成微信支付');
    for (const method of ['offline', 'online']) {
      expect(paymentLabel(0, method)).toBe('免费');
      expect(registrationNotice(0, method)).toContain('免费');
    }
  });
});
