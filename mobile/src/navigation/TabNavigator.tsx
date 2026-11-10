import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import type { TabParamList } from './types';
import { AccountScreen } from '../screens/AccountScreen';
import { PlaceholderScreen } from '../screens/PlaceholderScreen';

const Tab = createBottomTabNavigator<TabParamList>();

export function TabNavigator() {
  return (
    <Tab.Navigator initialRouteName="Groups">
      <Tab.Screen name="Friends">
        {() => <PlaceholderScreen title="Friends" />}
      </Tab.Screen>
      <Tab.Screen name="Groups">
        {() => <PlaceholderScreen title="Groups" />}
      </Tab.Screen>
      <Tab.Screen name="Activity">
        {() => <PlaceholderScreen title="Activity" />}
      </Tab.Screen>
      <Tab.Screen name="Account" component={AccountScreen} />
    </Tab.Navigator>
  );
}
