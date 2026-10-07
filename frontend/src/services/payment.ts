import { request } from "./api";
export async function requestPayment(params: any) {
  if (!params?.timeStamp || !params?.paySign)
    throw new Error("未获取到有效微信支付参数");
  await uni.requestPayment({
    provider: "wxpay",
    timeStamp: params.timeStamp,
    nonceStr: params.nonceStr,
    package: params.package,
    signType: params.signType,
    paySign: params.paySign,
  } as any);
}
export async function payTournament(id: number) {
  return requestPayment(
    await request(`/tournaments/${id}/pay`, { method: "POST" }),
  );
}
