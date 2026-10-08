import { describe, expect, it } from 'vitest';
import { postLocation } from '../src/domain/post-location';
describe('post meeting location', () => {
  it('uses a free post meeting point and never a club address', () => {
    expect(postLocation({ address:'河边网球场', city:'南京市',latitude:32,longitude:118,club_name:'俱乐部' })).toEqual({ title:'河边网球场',address:'河边网球场',latitude:32,longitude:118 });
  });
  it('uses the linked court rather than stale free-post coordinates', () => {
    expect(postLocation({venue_id:7,venue_name:'东区球场',venue_address:'长江路8号',venue_latitude:32,venue_longitude:118,address:'旧位置',latitude:30,longitude:110})).toEqual({title:'东区球场',address:'长江路8号',latitude:32,longitude:118});
  });
  it('keeps older coordinate-only posts navigable without inventing an address', () => {
    expect(postLocation({city:'南京市',latitude:32,longitude:118}).title).toBe('南京市 · 已选活动地点');
    expect(postLocation({}).title).toBe('地点待协商');
  });
});
