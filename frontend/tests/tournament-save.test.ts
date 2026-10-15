import { beforeEach, expect, it, vi } from 'vitest';
vi.mock('../src/services/api', () => ({ request: vi.fn() }));
import { request } from '../src/services/api';
import { saveTournament } from '../src/services/tournaments';
const api=vi.mocked(request);
beforeEach(()=>{api.mockReset();});
it.each([0,12])('saves only the current prize format once (id %s)',async id=>{
  api.mockResolvedValue({id:12});
  const data={title:'赛事',prizes:[{name:'冠军',description:'奖杯'}]};
  await saveTournament(data,id);
  expect(api).toHaveBeenCalledTimes(1);
  expect(api).toHaveBeenCalledWith(id?'/tournaments/12':'/tournaments',{method:id?'PUT':'POST',data});
});
it.each([400,409,422,500])('propagates failures without old-server retries (%s)',async statusCode=>{
  const error={statusCode,response:{data:{detail:[{type:'extra_forbidden',loc:['body','prizes']}]}}};
  api.mockRejectedValue(error);
  await expect(saveTournament({prizes:[]})).rejects.toEqual(error);
  expect(api).toHaveBeenCalledTimes(1);
});
