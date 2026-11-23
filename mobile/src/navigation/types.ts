import type { NavigatorScreenParams } from '@react-navigation/native';
import type { PersonDraft } from '../people/types';

export type AuthStackParamList = {
  Welcome: undefined;
  SignUp: undefined;
  LogIn: { email?: string } | undefined;
  SessionExpired: { email: string };
  /** SCR-06: opened from a reset link. */
  PasswordReset: { token: string };
};

export type TabParamList = {
  Friends: undefined;
  Groups: undefined;
  Activity: undefined;
  Account: undefined;
};

export type AddPeopleMode =
  | { kind: 'friend' }
  | { kind: 'group-create' }
  | { kind: 'group-members'; groupId: string };

export type MainStackParamList = {
  Tabs: NavigatorScreenParams<TabParamList> | undefined;
  AddPeople: { mode: AddPeopleMode; selected?: PersonDraft[] };
  CreateGroup: { picked?: PersonDraft[] } | undefined;
  GroupDetail: { groupId: string };
  /** SCR-13 members view (CR-UI-1): full member list, add people, invite, remove. */
  GroupMembers: { groupId: string };
  GroupSettings: { groupId: string };
  GroupBalances: { groupId: string };
  SimplifyExplainer: { groupId: string };
  /** SCR-22: add (groupId or friendId gives the context) or edit (expenseId). */
  ExpenseForm: { groupId?: string; friendId?: string; expenseId?: string };
  ExpenseDetail: { expenseId: string };
  FriendDetail: { friendId: string };
  FriendSettings: { friendId: string };
  /** SCR-30: exactly one of groupId (group scope) or friendId (friend scope). */
  SettleUp: { groupId?: string; friendId?: string };
  /**
   * SCR-31: record (from, to, amount prefilled from the tapped balance) or edit (settlementId).
   * owedMinor is what the payer owes in `currency` (for the overpay confirmation); omit when unknown.
   */
  RecordPayment: {
    settlementId?: string;
    groupId?: string | null;
    fromUserId?: string;
    toUserId?: string;
    amountMinor?: number;
    currency?: string;
    owedMinor?: number;
  };
  PaymentDetail: { settlementId: string };
  /** SCR-34. */
  NotificationSettings: undefined;
  /** SCR-17. */
  InviteLink: { groupId: string };
  /** SCR-18: opened from an invite link; the preview endpoint is not in the contract (D-C). */
  JoinGroup: { token: string };
  /** Add-friend link: adds by friend code (no lookup endpoint, D-C). */
  AddFriendByCode: { code: string };
  /** SCR-42 (my code only; scan is Blocked, D-C). */
  MyCode: undefined;
  /** SCR-33: remind `toUserId` (optionally within a group) about `amountMinor`. */
  Remind: {
    toUserId: string;
    toName: string;
    groupId?: string | null;
    amountMinor?: number;
    currency?: string;
  };
  /** SCR-39. */
  Paywall: { reason?: 'search' | 'export' | 'receipt' } | undefined;
  /** SCR-36. */
  Search: undefined;
  /** SCR-38: exactly one of groupId / friendId. */
  ExportSheet: { groupId?: string; friendId?: string };
};

export type RootStackParamList = {
  Auth: NavigatorScreenParams<AuthStackParamList> | undefined;
  Main: NavigatorScreenParams<MainStackParamList> | undefined;
};
