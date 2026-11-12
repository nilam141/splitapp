import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { MainStackParamList } from './types';
import { TabNavigator } from './TabNavigator';
import { AddPeopleScreen } from '../screens/AddPeopleScreen';
import { CreateGroupScreen } from '../screens/CreateGroupScreen';
import { GroupDetailScreen } from '../screens/GroupDetailScreen';
import { GroupSettingsScreen } from '../screens/GroupSettingsScreen';
import { GroupBalancesScreen } from '../screens/GroupBalancesScreen';
import { SimplifyExplainerScreen } from '../screens/SimplifyExplainerScreen';
import { ExpenseFormScreen } from '../screens/ExpenseFormScreen';
import { ExpenseDetailScreen } from '../screens/ExpenseDetailScreen';
import { FriendDetailScreen } from '../screens/FriendDetailScreen';
import { FriendSettingsScreen } from '../screens/FriendSettingsScreen';

const Stack = createNativeStackNavigator<MainStackParamList>();

// Signed-in screens: the tab shell with the flows that open above it.
export function MainNavigator() {
  return (
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
    </Stack.Navigator>
  );
}
