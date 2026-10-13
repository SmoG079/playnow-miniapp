import { request } from "./api";

/** wx.requestPayment 参数，由后端统一下单后返回 */
export interface PayParams {
  timeStamp: string;
  nonceStr: string;
  package: string;
  signType: string;
  paySign: string;
}

/** 用户主动取消支付时抛出，与真实失败区分开，页面可据此保留订单 */
function cancelledError() {
  return Object.assign(new Error("已取消支付"), { cancelled: true });
}

export async function requestPayment(params: PayParams) {
  if (!params?.timeStamp || !params?.paySign)
    throw new Error("未获取到有效微信支付参数");
  try {
    await uni.requestPayment({
      provider: "wxpay",
      timeStamp: params.timeStamp,
      nonceStr: params.nonceStr,
      package: params.package,
      signType: params.signType,
      paySign: params.paySign,
    } as any);
  } catch (e: any) {
    const detail = String(e?.errMsg || e?.message || "");
    if (/cancel/i.test(detail)) throw cancelledError();
    throw Object.assign(new Error("支付失败，请重试"), { cause: e });
  }
}

/**
 * 2026-10-13：订场临时占位确认，不调用微信收银台、不产生真实收款。
 * 后端确认订单及全部时段后返回；真实支付调用保留注释，待验收后恢复。
 */
export async function payBooking(bookingId: number | string) {
  const result = await request<any>(`/bookings/${bookingId}/pay`, {
    method: "POST",
  });
  // 真实订场支付暂缓，恢复时需同步启用后端预支付及微信回调验收。
  // if (result?.pay_params) await requestPayment(result.pay_params as PayParams);
  return result;
}

export async function payTournament(id: number) {
  return requestPayment(
    await request(`/tournaments/${id}/pay`, { method: "POST" }),
  );
}
