import {afterEach,describe,expect,it,vi} from 'vitest';
vi.mock('../src/services/api',()=>({request:vi.fn()}));
import {request} from '../src/services/api';
import {payBooking} from '../src/services/payment';
afterEach(()=>{vi.unstubAllGlobals();vi.clearAllMocks();});
describe('temporary booking confirmation',()=>{
  it('confirms with the backend and never opens the real cashier',async()=>{
    const cashier=vi.fn();vi.stubGlobal('uni',{requestPayment:cashier});
    const response={payment_mode:'placeholder',pay_params:{timeStamp:'1',paySign:'unused'}};
    vi.mocked(request).mockResolvedValue(response);
    expect(await payBooking(12)).toBe(response);
    expect(request).toHaveBeenCalledWith('/bookings/12/pay',{method:'POST'});
    expect(cashier).not.toHaveBeenCalled();
  });
});
