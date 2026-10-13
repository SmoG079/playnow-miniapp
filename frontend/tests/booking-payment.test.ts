import {afterEach,describe,expect,it,vi} from 'vitest';
vi.mock('../src/services/api',()=>({request:vi.fn()}));
import {request} from '../src/services/api';
import {confirmBookingPaid,payBooking,syncBookingPayment,syncBookingRefund} from '../src/services/payment';
afterEach(()=>{vi.unstubAllGlobals();vi.clearAllMocks();});
const params={timeStamp:'1',nonceStr:'n',package:'prepay_id=x',signType:'RSA',paySign:'sig'};
describe('booking payment',()=>{
  it('opens the cashier with the pay params returned by the backend',async()=>{
    const cashier=vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('uni',{requestPayment:cashier});
    const response={payment_mode:'wechat',pay_params:params};
    vi.mocked(request).mockResolvedValue(response);
    expect(await payBooking(12)).toBe(response);
    expect(request).toHaveBeenCalledWith('/bookings/12/pay',{method:'POST'});
    expect(cashier).toHaveBeenCalledWith(expect.objectContaining({provider:'wxpay',paySign:'sig'}));
  });
  it('keeps working when the backend returns no pay params (placeholder mode)',async()=>{
    const cashier=vi.fn();vi.stubGlobal('uni',{requestPayment:cashier});
    const response={payment_mode:'placeholder'};
    vi.mocked(request).mockResolvedValue(response);
    expect(await payBooking(12)).toBe(response);
    expect(cashier).not.toHaveBeenCalled();
  });
  it('marks user cancellation so the page can keep the order',async()=>{
    vi.stubGlobal('uni',{requestPayment:vi.fn().mockRejectedValue({errMsg:'requestPayment:fail cancel'})});
    vi.mocked(request).mockResolvedValue({pay_params:params});
    await expect(payBooking(12)).rejects.toMatchObject({cancelled:true});
  });
});
describe('payment sync fallback (callback may be unreachable)',()=>{
  it('asks the backend to query WeChat for the real payment result',async()=>{
    vi.mocked(request).mockResolvedValue({status:'paid'});
    expect(await syncBookingPayment(12)).toEqual({status:'paid'});
    expect(request).toHaveBeenCalledWith('/bookings/12/sync-payment',{method:'POST'});
  });
  it('stops polling as soon as the order is confirmed paid',async()=>{
    vi.mocked(request).mockResolvedValueOnce({status:'pending'}).mockResolvedValueOnce({status:'paid'});
    expect(await confirmBookingPaid(12,{attempts:4,intervalMs:1})).toBe('paid');
    expect(request).toHaveBeenCalledTimes(2);
  });
  it('reports pending after exhausting attempts without throwing',async()=>{
    vi.mocked(request).mockResolvedValue({status:'pending'});
    expect(await confirmBookingPaid(12,{attempts:3,intervalMs:1})).toBe('pending');
    expect(request).toHaveBeenCalledTimes(3);
  });
  it('keeps polling when a single sync call fails',async()=>{
    vi.mocked(request).mockRejectedValueOnce(new Error('502')).mockResolvedValueOnce({status:'paid'});
    expect(await confirmBookingPaid(12,{attempts:3,intervalMs:1})).toBe('paid');
    expect(request).toHaveBeenCalledTimes(2);
  });
});
describe('refund sync fallback (refund callback shares the same unreachable callback URL)',()=>{
  it('asks the backend to query WeChat for the real refund result',async()=>{
    vi.mocked(request).mockResolvedValue({status:'refunded',refund_status:'success'});
    expect(await syncBookingRefund(12)).toEqual({status:'refunded',refund_status:'success'});
    expect(request).toHaveBeenCalledWith('/bookings/12/sync-refund',{method:'POST'});
  });
  it('returns the still-processing state without throwing',async()=>{
    vi.mocked(request).mockResolvedValue({status:'refunding'});
    expect(await syncBookingRefund(12)).toEqual({status:'refunding'});
  });
  it('propagates failures so the page can tell the user to retry',async()=>{
    vi.mocked(request).mockRejectedValue(new Error('查询退款结果失败，请稍后重试'));
    await expect(syncBookingRefund(12)).rejects.toThrow('查询退款结果失败');
  });
});
