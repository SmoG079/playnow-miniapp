interface Registration {
  user_id: string;
  user_nickname?: string;
  user_avatar?: string;
  status: string;
}

interface PostParticipants {
  user_id: string;
  user_nickname?: string;
  user_avatar?: string;
  registrations?: Registration[];
}

export function postParticipants(post: PostParticipants) {
  return [
    { id: post.user_id, nickname: post.user_nickname || '球友', avatar: post.user_avatar, organizer: true },
    ...(post.registrations || [])
      .filter(r => r.status === 'approved' && r.user_id !== post.user_id)
      .map(r => ({ id: r.user_id, nickname: r.user_nickname || '球友', avatar: r.user_avatar, organizer: false })),
  ];
}
