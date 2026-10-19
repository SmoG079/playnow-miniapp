import {describe,it,expect,vi} from 'vitest';
vi.mock('../src/services/api',()=>({request:vi.fn()}));
import {request} from '../src/services/api';
import {mergeMessages,newMessageKey,getMessages,sendMessage,markMessagesRead,type DirectMessage} from '../src/services/messages';
const message=(id:number):DirectMessage=>({id,client_id:'msg_'+id,content:'消息'+id,is_mine:false,created_at:'2026-10-14T01:00:00'});
describe('private messages',()=>{
 it('deduplicates polling, retry and history while keeping sequence',()=>{
  expect(mergeMessages([message(3),message(4)],[message(2),message(3),message(5)]).map(m=>m.id)).toEqual([2,3,4,5]);
 });
 it('uses a stable client key supplied by the caller for retries',async()=>{
  vi.mocked(request).mockResolvedValue(message(1));
  const key=newMessageKey();expect(key).toMatch(/^msg_[a-z0-9_]+$/);expect(key.length).toBeLessThanOrEqual(64);
  await sendMessage('abc','一起来打球',key);await sendMessage('abc','一起来打球',key);
  expect(request).toHaveBeenLastCalledWith('/messages/conversations/abc/messages',{method:'POST',data:{content:'一起来打球',client_id:key}});
 });
 it('supports history and polling cursors and acknowledges only the fetched boundary',async()=>{
  vi.mocked(request).mockResolvedValue({items:[],has_more:false});
  await getMessages('abc',{after:0});expect(request).toHaveBeenLastCalledWith('/messages/conversations/abc/messages?page_size=30&after_id=0');
  await getMessages('abc',{before:30});expect(request).toHaveBeenLastCalledWith('/messages/conversations/abc/messages?page_size=30&before_id=30');
  await markMessagesRead('abc',20);expect(request).toHaveBeenLastCalledWith('/messages/conversations/abc/read',{method:'POST',data:{through_id:20},preservePage:true});
 });
});
