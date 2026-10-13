import {describe,it,expect} from 'vitest';
import {registrationClosed,registrationCutoff,visibleInDiscovery,activityPhase} from '../src/domain/activity-visibility';
import {cardState} from '../src/domain/activity-card';
import {notificationTime} from '../src/domain/notifications';
describe('registration expiry',()=>{
  const now=Date.parse('2026-10-13T09:00:00Z');
  it('removes a post at Shanghai start time, retaining full future posts',()=>{
    const post={status:'open',preferred_date:'2026-10-13',preferred_start:'17:00'};
    expect(registrationCutoff(post,'post')).toBe(now);
    expect(visibleInDiscovery(post,'post',now-1)).toBe(true);
    expect(visibleInDiscovery(post,'post',now)).toBe(false);
    expect(visibleInDiscovery({...post,status:'full',preferred_start:'18:00'},'post',now)).toBe(true);
  });
  it('uses tournament deadline before the event starts and handles offsets',()=>{
    const t={status:'open',start_time:'2026-10-14T01:00:00',registration_deadline:'2026-10-13T17:00:00+08:00'};
    expect(registrationClosed(t,'tournament',now)).toBe(true);
    expect(visibleInDiscovery(t,'tournament',now-1)).toBe(true);
    expect(cardState({status:'open',phase:'registration_closed'},null).label).toBe('报名截止，等待开始');
  });
  it('handles manual closure and legacy missing deadlines without inventing valid times',()=>{
    expect(visibleInDiscovery({status:'open',start_time:'2026-10-14T01:00:00',registration_closed:true},'tournament',now)).toBe(true);
    expect(visibleInDiscovery({status:'open',start_time:'2026-10-14T01:00:00'},'tournament',now)).toBe(true);
    expect(visibleInDiscovery({status:'open'},'post',now)).toBe(false);
  });
});
it('keeps notification timestamps compact and in Shanghai time',()=>{
  expect(notificationTime('2026-10-13T01:30:00')).toBe('10-13 09:30');
  expect(notificationTime('2026-10-13T01:30:00',true)).toBe('2026-10-13 09:30');
  expect(notificationTime('invalid')).toBe('');
});

it('keeps waiting and live tournaments until their end and labels posts ended at start',()=>{
  const t={status:'open',registration_deadline:'2026-10-13T00:00:00Z',start_time:'2026-10-13T01:00:00Z',end_time:'2026-10-13T03:00:00Z'};
  expect(activityPhase(t,'tournament',Date.parse('2026-10-13T00:00:00Z'))).toBe('registration_closed');
  expect(activityPhase(t,'tournament',Date.parse(t.start_time))).toBe('ongoing');
  expect(visibleInDiscovery(t,'tournament',Date.parse(t.end_time))).toBe(false);
  expect(activityPhase({status:'open',preferred_date:'2026-10-13',preferred_start:'09:00'},'post',Date.parse(t.start_time))).toBe('ended');
});
