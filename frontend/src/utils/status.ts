export const bookingStatus: Record<string, string> = {
  pending: "待支付",
  paid: "已支付",
  completed: "已完成",
  cancelled: "已取消",
  refunding: "退款中",
  refunded: "已退款",
};
export const settlementStatus: Record<string, string> = {
  pending: "待分账",
  processing: "处理中",
  completed: "已完成",
  failed: "失败",
};
