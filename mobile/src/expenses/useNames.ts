import { useCallback, useMemo } from 'react';
import { useGetGroup, useListFriends } from '../api/generated/splitapp';
import { useAuth } from '../auth/AuthContext';

/**
 * Resolves a user id to a display name: "You", then a member of the given group, or a friend.
 * groupId: a group id = group members only; null = non-group, uses the friends list; undefined = not known yet
 * (nothing is fetched).
 */
export function useNameOf(groupId?: string | null) {
  const { user } = useAuth();
  const friends = useListFriends(undefined, {
    query: { enabled: groupId === null },
  });
  const group = useGetGroup(groupId ?? '', {
    query: { enabled: !!groupId },
  });
  const names = useMemo(() => {
    const map = new Map<string, string>();
    if (friends.data?.status === 200) {
      friends.data.data.items.forEach(f => map.set(f.user.id, f.user.name));
    }
    if (group.data?.status === 200) {
      group.data.data.members.forEach(m => map.set(m.user.id, m.user.name));
    }
    return map;
  }, [friends.data, group.data]);
  return useCallback(
    (id: string) => (id === user?.id ? 'You' : (names.get(id) ?? 'Someone')),
    [names, user?.id],
  );
}
