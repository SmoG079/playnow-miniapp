import { describe, expect, it } from 'vitest';
import { postParticipants } from '../src/domain/post-participants';

describe('post participant roster', () => {
  it('includes the organizer and only approved registrations, keeping their public profiles', () => {
    const people = postParticipants({ user_id: 'owner', user_nickname: '发起人昵称', user_avatar: 'owner.jpg', registrations: [
      { user_id: 'waiting', status: 'pending', user_nickname: '待审核' },
      { user_id: 'alice', status: 'approved', user_nickname: '爱打球的 Alice', user_avatar: 'alice.jpg' },
      { user_id: 'cancelled', status: 'cancelled' },
      { user_id: 'rejected', status: 'rejected' },
    ] });
    expect(people).toEqual([
      { id: 'owner', nickname: '发起人昵称', avatar: 'owner.jpg', organizer: true },
      { id: 'alice', nickname: '爱打球的 Alice', avatar: 'alice.jpg', organizer: false },
    ]);
  });
  it('shows the organizer before anyone else has registered and does not duplicate them', () => {
    expect(postParticipants({ user_id: 'owner' })).toEqual([{ id: 'owner', nickname: '球友', avatar: undefined, organizer: true }]);
    expect(postParticipants({ user_id: 'owner', registrations: [{ user_id: 'owner', status: 'approved' }] })).toHaveLength(1);
  });
});
