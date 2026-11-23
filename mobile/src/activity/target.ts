import type { ActivityItem } from '../api/generated/model';
import type { MainStackParamList } from '../navigation/types';

export type ActivityTarget = {
  [K in keyof MainStackParamList]: { name: K; params: MainStackParamList[K] };
}[keyof MainStackParamList];

/** Tap-through (screens.md SCR-10): expense -> SCR-29, payment -> SCR-32, group -> SCR-13. Undefined = not tappable. */
export function activityTarget(item: ActivityItem): ActivityTarget | undefined {
  switch (item.entity_type) {
    case 'expense':
      return { name: 'ExpenseDetail', params: { expenseId: item.entity_id } };
    case 'settlement':
      return {
        name: 'PaymentDetail',
        params: { settlementId: item.entity_id },
      };
    case 'group':
      return item.action === 'group.deleted'
        ? undefined
        : { name: 'GroupDetail', params: { groupId: item.entity_id } };
    case 'comment':
      return item.group_id
        ? { name: 'GroupDetail', params: { groupId: item.group_id } }
        : undefined;
    case 'friendship':
      return item.action === 'friend.added'
        ? { name: 'FriendDetail', params: { friendId: item.entity_id } }
        : undefined;
    default:
      return undefined;
  }
}
