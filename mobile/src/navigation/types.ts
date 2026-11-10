import type { NavigatorScreenParams } from '@react-navigation/native';
import type { PersonDraft } from '../people/types';

export type AuthStackParamList = {
  Welcome: undefined;
  SignUp: undefined;
  LogIn: { email?: string } | undefined;
  SessionExpired: { email: string };
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
  GroupSettings: { groupId: string };
  /** SCR-22: add (groupId or friendId gives the context) or edit (expenseId). */
  ExpenseForm: { groupId?: string; friendId?: string; expenseId?: string };
  ExpenseDetail: { expenseId: string };
  FriendDetail: { friendId: string };
  FriendSettings: { friendId: string };
};

export type RootStackParamList = {
  Auth: NavigatorScreenParams<AuthStackParamList> | undefined;
  Main: NavigatorScreenParams<MainStackParamList> | undefined;
};
