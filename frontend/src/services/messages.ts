import { request, type PageResult } from './api';
export interface Conversation {id:string;peer:{nickname:string;avatar_url?:string};activity:{id:number;kind:"post"|"tournament";title:string};last_message?:string;last_message_at?:string;unread_count:number}
export interface DirectMessage {id:number;client_id:string;content:string;is_mine:boolean;created_at:string}
export interface History {items:DirectMessage[];has_more:boolean}
export function getConversations(page=1){return request<PageResult<Conversation>>(`/messages/conversations?page=${page}&page_size=20`);}
export function getConversation(id:string){return request<Conversation>(`/messages/conversations/${encodeURIComponent(id)}`);}
export function getMessages(id:string,cursor?:{before?:number;after?:number}){
  const extra=cursor?.before!=null?'&before_id='+cursor.before:cursor?.after!=null?'&after_id='+cursor.after:'';
  return request<History>(`/messages/conversations/${encodeURIComponent(id)}/messages?page_size=30${extra}`);
}
export function sendMessage(id:string,content:string,clientId:string){return request<DirectMessage>(`/messages/conversations/${encodeURIComponent(id)}/messages`,{method:'POST',data:{content,client_id:clientId}});}
export function markMessagesRead(id:string,through:number){return request(`/messages/conversations/${encodeURIComponent(id)}/read`,{method:'POST',data:{through_id:through}});}
export function mergeMessages(current:DirectMessage[],incoming:DirectMessage[]){
  return [...new Map([...current,...incoming].map(m=>[m.id,m])).values()].sort((a,b)=>a.id-b.id);
}
export function newMessageKey(){return 'msg_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2)+'_'+Math.random().toString(36).slice(2);}
