import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { MainStackParamList } from './types';
import { TabNavigator } from './TabNavigator';
import { AddPeopleScreen } from '../screens/AddPeopleScreen';
import { CreateGroupScreen } from '../screens/CreateGroupScreen';
import { GroupDetailScreen } from '../screens/GroupDetailScreen';
import { GroupSettingsScreen } from '../screens/GroupSettingsScreen';

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
    </Stack.Navigator>
  );
}
