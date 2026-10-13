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
 * 订场支付：后端统一下单后返回 wx.requestPayment 参数，前端调起收银台。
 * 后端 WX_PAY_ENABLED=false（本地/CI）时不返回 pay_params，此时直接返回占位结果。
 * 用户取消支付会抛出带 cancelled 标记的异常，页面据此保留订单便于重试。
 */
export async function payBooking(bookingId: number | string) {
  const result = await request<any>(`/bookings/${bookingId}/pay`, {
    method: "POST",
  });
  if (result?.pay_params) await requestPayment(result.pay_params as PayParams);
  return result;
}

export async function payTournament(id: number) {
  return requestPayment(
    await request(`/tournaments/${id}/pay`, { method: "POST" }),
  );
}

/**
 * 主动查单兜底：请后端向微信查询本单真实支付结果并同步。
 *
 * 正常链路是微信回调后端；当回调不可达（例如回调域名尚未完成 ICP 备案、
 * 443 被拦截）时订单会一直停在 pending，而款项其实已经收到。此接口让前端
 * 主动补齐状态，返回同步后的订单状态。
 */
export async function syncBookingPayment(bookingId: number | string) {
  return request<{ msg: string; order_no: string; status: string }>(
    `/bookings/${bookingId}/sync-payment`,
    { method: "POST" },
  );
}

/**
 * 支付完成后确认订单是否已记账。
 *
 * 收银台返回成功 ≠ 后端已把订单标记为已支付（微信回调可能延迟或不可达），
 * 因此主动查单若干次；命中 paid 立即返回。
 * 查询本身失败不抛错，交由调用方按 pending 处理（页面仍可展示"处理中"）。
 */
export async function confirmBookingPaid(
  bookingId: number | string,
  { attempts = 4, intervalMs = 1500 } = {},
) {
  let status = "pending";
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await syncBookingPayment(bookingId);
      if (res?.status) status = res.status;
    } catch {
      // 查询失败不阻断：保持当前状态，由页面提示用户稍后查看
    }
    if (status !== "pending") return status;
    if (i < attempts - 1)
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return status;
}

/**
 * 主动查退款兜底：请后端向微信查询本单退款进度并同步。
 *
 * 退款与支付共用同一个回调地址，回调不可达时订单会一直停在 refunding，
 * 而款项其实已经退回。后端还有 Celery 定时任务兜底（最长约 5 分钟），
 * 此接口用于用户/管理员即时确认退款结果。
 */
export async function syncBookingRefund(bookingId: number | string) {
  return request<{
    msg: string;
    order_no: string;
    status: string;
    refund_status?: string;
  }>(`/bookings/${bookingId}/sync-refund`, { method: "POST" });
}
