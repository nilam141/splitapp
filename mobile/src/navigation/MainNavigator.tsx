import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { MainStackParamList } from './types';
import { TabNavigator } from './TabNavigator';
import { AddPeopleScreen } from '../screens/AddPeopleScreen';
import { CreateGroupScreen } from '../screens/CreateGroupScreen';
import { GroupDetailScreen } from '../screens/GroupDetailScreen';
import { GroupMembersScreen } from '../screens/GroupMembersScreen';
import { GroupSettingsScreen } from '../screens/GroupSettingsScreen';
import { GroupBalancesScreen } from '../screens/GroupBalancesScreen';
import { SimplifyExplainerScreen } from '../screens/SimplifyExplainerScreen';
import { ExpenseFormScreen } from '../screens/ExpenseFormScreen';
import { ExpenseDetailScreen } from '../screens/ExpenseDetailScreen';
import { FriendDetailScreen } from '../screens/FriendDetailScreen';
import { FriendSettingsScreen } from '../screens/FriendSettingsScreen';
import { SettleUpScreen } from '../screens/SettleUpScreen';
import { RecordPaymentScreen } from '../screens/RecordPaymentScreen';
import { PaymentDetailScreen } from '../screens/PaymentDetailScreen';
import { NotificationSettingsScreen } from '../screens/NotificationSettingsScreen';
import { InviteLinkScreen } from '../screens/InviteLinkScreen';
import { JoinGroupScreen } from '../screens/JoinGroupScreen';
import { AddFriendByCodeScreen } from '../screens/AddFriendByCodeScreen';
import { MyCodeScreen } from '../screens/MyCodeScreen';
import { RemindScreen } from '../screens/RemindScreen';
import { PaywallScreen } from '../screens/PaywallScreen';
import { SearchScreen } from '../screens/SearchScreen';
import { ExportSheetScreen } from '../screens/ExportSheetScreen';
import { SyncStatusBar } from '../components/SyncStatusBar';
import { SnackbarHost } from '../components/SnackbarHost';

const Stack = createNativeStackNavigator<MainStackParamList>();

// Signed-in screens: the tab shell with the flows that open above it.
export function MainNavigator() {
  return (
    <>
      <Stack.Navigator>
        <Stack.Screen
          name="Tabs"
          component={TabNavigator}
          options={{ headerShown: false }}
        />
        <Stack.Screen
          name="AddPeople"
          component={AddPeopleScreen}
          options={{ title: 'Add people' }}
        />
        <Stack.Screen
          name="CreateGroup"
          component={CreateGroupScreen}
          options={{ title: 'New group' }}
        />
        <Stack.Screen
          name="GroupDetail"
          component={GroupDetailScreen}
          options={{ title: 'Group' }}
        />
        <Stack.Screen
          name="GroupMembers"
          component={GroupMembersScreen}
          options={{ title: 'Members' }}
        />
        <Stack.Screen
          name="GroupSettings"
          component={GroupSettingsScreen}
          options={{ title: 'Group settings' }}
        />
        <Stack.Screen
          name="GroupBalances"
          component={GroupBalancesScreen}
          options={{ title: 'Balances' }}
        />
        <Stack.Screen
          name="SimplifyExplainer"
          component={SimplifyExplainerScreen}
          options={{ title: 'Simplify debts' }}
        />
        <Stack.Screen
          name="ExpenseForm"
          component={ExpenseFormScreen}
          options={{ title: 'Add expense' }}
        />
        <Stack.Screen
          name="ExpenseDetail"
          component={ExpenseDetailScreen}
          options={{ title: 'Expense' }}
        />
        <Stack.Screen
          name="FriendDetail"
          component={FriendDetailScreen}
          options={{ title: 'Friend' }}
        />
        <Stack.Screen
          name="FriendSettings"
          component={FriendSettingsScreen}
          options={{ title: 'Friend settings' }}
        />
        <Stack.Screen
          name="SettleUp"
          component={SettleUpScreen}
          options={{ title: 'Settle up' }}
        />
        <Stack.Screen
          name="RecordPayment"
          component={RecordPaymentScreen}
          options={{ title: 'Record payment' }}
        />
        <Stack.Screen
          name="PaymentDetail"
          component={PaymentDetailScreen}
          options={{ title: 'Payment' }}
        />
        <Stack.Screen
          name="NotificationSettings"
          component={NotificationSettingsScreen}
          options={{ title: 'Notifications' }}
        />
        <Stack.Screen
          name="InviteLink"
          component={InviteLinkScreen}
          options={{ title: 'Invite link' }}
        />
        <Stack.Screen
          name="JoinGroup"
          component={JoinGroupScreen}
          options={{ title: 'Join group' }}
        />
        <Stack.Screen
          name="AddFriendByCode"
          component={AddFriendByCodeScreen}
          options={{ title: 'Add friend' }}
        />
        <Stack.Screen
          name="MyCode"
          component={MyCodeScreen}
          options={{ title: 'My code' }}
        />
        <Stack.Screen
          name="Remind"
          component={RemindScreen}
          options={{ title: 'Remind' }}
        />
        <Stack.Screen
          name="Paywall"
          component={PaywallScreen}
          options={{ title: 'Premium' }}
        />
        <Stack.Screen
          name="Search"
          component={SearchScreen}
          options={{ title: 'Search' }}
        />
        <Stack.Screen
          name="ExportSheet"
          component={ExportSheetScreen}
          options={{ title: 'Export' }}
        />
      </Stack.Navigator>
      <SyncStatusBar />
      <SnackbarHost />
    </>
  );
}
