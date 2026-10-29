export type PaymentMethod = 'offline' | 'online';

export function paymentLabel(fee: number | string | null | undefined, method: string | undefined) {
  if (!(Number(fee) > 0)) return '免费';
  return method === 'online' ? '线上付款' : '线下付款';
}

export function registrationNotice(fee: number | string | null | undefined, method: string | undefined) {
  if (!(Number(fee) > 0)) return '本次活动免费，确认报名？';
  const amount = Number(fee).toFixed(2);
  return method === 'online'
    ? `报名费 ¥${amount}/人，需在线上完成微信支付。确认报名？`
    : `报名费 ¥${amount}/人，采用线下付款。报名时无需线上支付，报名成功后由组织者自行组织收款。确认报名？`;
}
