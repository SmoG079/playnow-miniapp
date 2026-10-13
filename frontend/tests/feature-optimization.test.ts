import {describe,it,expect} from 'vitest';
import {normalizedPrizes,displayedPrizes} from '../src/domain/prizes';
import {swapSeats,seatError} from '../src/domain/draw-adjustment';
describe('optional prizes',()=>{
  it('preserves newlines and removes empty rows',()=>expect(normalizedPrizes([{name:' ',description:''},{name:' 冠军 ',description:'奖杯\n奖金'}])).toEqual([{name:'冠军',description:'奖杯\n奖金'}]));
  it('uses legacy only when structured data absent',()=>{expect(displayedPrizes(null,'旧奖项')).toHaveLength(1);expect(displayedPrizes([],'旧奖项')).toEqual([]);});
});
describe('draw seat exchanges',()=>{
  const seats=[{group_no:1,position:0,team_id:1},{group_no:1,position:1,team_id:2},{group_no:2,position:0,team_id:3},{group_no:2,position:1,team_id:4}];
  it('swaps whole units across groups without modifying source',()=>{const result=swapSeats(seats,0,2);expect(result[0].team_id).toBe(3);expect(result[2].team_id).toBe(1);expect(seats[0].team_id).toBe(1);expect(seatError(seats,result,true)).toBeUndefined();});
  it('rejects duplicate entrants',()=>expect(seatError(seats,seats.map((s,i)=>({...s,team_id:i===0?2:s.team_id})),true)).toBeTruthy());
  it('rejects moving byes across groups or making double byes',()=>{const byes=[1,null,2,null].map((team_id,position)=>({group_no:1,position,team_id}));expect(seatError(byes,swapSeats(byes,1,2),true)).toBeTruthy();const grouped=byes.map((s,i)=>({...s,group_no:i<2?1:2,position:i%2}));expect(seatError(grouped,swapSeats(grouped,0,3),true)).toContain('各组');});
});

import {drawBlockReason} from '../src/domain/draw-readiness';
import type {Tournament} from '../src/services/tournaments';
describe('draw eligibility',()=>{
  const fixture={config:{discipline:'singles',group_count:1},registrations:[{status:'confirmed',admission:'active',approval:'approved',payment:'none'}]} as Tournament;
  it('blocks a single eligible participant',()=>expect(drawBlockReason(fixture)).toContain('当前 1 名'));
  it('prefers server pairing validation',()=>expect(drawBlockReason({...fixture,draw_block_reason:'第1组尚有未配对人员'})).toContain('未配对'));
  it('does not evaluate initial roster in knockout stage',()=>expect(drawBlockReason({...fixture,draw_stage:'knockout'})).toBe(''));
});

import {decodeRouteText} from '../src/utils/navigation';
it('normalizes booking return venue names without corrupting plain or malformed names',()=>{
  expect(decodeRouteText(encodeURIComponent('1号网球场'))).toBe('1号网球场');
  expect(decodeRouteText('1号网球场')).toBe('1号网球场');
  expect(decodeRouteText('场地100%')).toBe('场地100%');
});
