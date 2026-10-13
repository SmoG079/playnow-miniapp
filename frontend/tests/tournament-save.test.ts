import { beforeEach, describe, expect, it, vi } from 'vitest';
vi.mock('../src/services/api', () => ({ request: vi.fn() }));
import { request } from '../src/services/api';
import { saveTournament } from '../src/services/tournaments';
const api = vi.mocked(request);
const unsupported = () => Object.assign(new Error('Extra inputs are not permitted'), {
  statusCode:422, response:{data:{detail:[{type:'extra_forbidden',loc:['body','prizes']}]}}
});
beforeEach(() => api.mockReset());
describe('tournament save across backend versions', () => {
  it('preserves explicit empty prizes on upgraded backends without retry', async () => {
    api.mockResolvedValue({id:1});
    await saveTournament({title:'测试赛事',prize:'旧内容',prizes:[]});
    expect(api).toHaveBeenCalledTimes(1);
    expect(api).toHaveBeenCalledWith('/tournaments',{method:'POST',data:{title:'测试赛事',prize:'旧内容',prizes:[]}});
  });
  it.each([0,12])('retries only the rejected empty field and clears legacy content (id %s)', async id => {
    api.mockRejectedValueOnce(unsupported()).mockResolvedValueOnce({id:12});
    const data={title:'测试赛事',prize:'旧内容',prizes:[],config:{format:'knockout'}};
    await expect(saveTournament(data,id)).resolves.toEqual({id:12});
    expect(api).toHaveBeenLastCalledWith(id?'/tournaments/12':'/tournaments',{method:id?'PUT':'POST',data:{title:'测试赛事',prize:'',config:{format:'knockout'}}});
    expect(data.prize).toBe('旧内容');expect(data.prizes).toEqual([]);
  });
  it('never drops populated prizes to make an old backend accept the event', async () => {
    api.mockRejectedValueOnce(unsupported());
    await expect(saveTournament({prizes:[{name:'冠军',description:'奖金'}]})).rejects.toThrow('升级后端');
    expect(api).toHaveBeenCalledTimes(1);
  });
  it.each([400,409,422,500])('does not retry other failures (%s)', async statusCode => {
    const error={statusCode,response:{data:{detail:[{type:'value_error',loc:['body','title']}]}}};
    api.mockRejectedValueOnce(error);
    await expect(saveTournament({prizes:[]})).rejects.toEqual(error);
    expect(api).toHaveBeenCalledTimes(1);
  });
});
