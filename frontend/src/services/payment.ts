import { request } from "./api";
export async function requestPayment(params: any) {
  if (!params?.timeStamp) return;
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
