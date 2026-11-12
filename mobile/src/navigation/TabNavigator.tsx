import React, { useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import {
  BottomTabBar,
  BottomTabBarProps,
  createBottomTabNavigator,
} from '@react-navigation/bottom-tabs';
import type { TabParamList } from './types';
import { DEFAULT_TAB, loadLastTab, saveLastTab } from './lastTab';
import { AccountScreen } from '../screens/AccountScreen';
import { FriendsScreen } from '../screens/FriendsScreen';
import { GroupsScreen } from '../screens/GroupsScreen';
import { PlaceholderScreen } from '../screens/PlaceholderScreen';
import { LoadingView } from '../components/StateViews';

// The feed itself ships in a later slice.
const ActivityPlaceholder = () => <PlaceholderScreen title="Activity" />;

const Tab = createBottomTabNavigator<TabParamList>();

// SCR-07 add-expense button. The expense form (SCR-22) ships in a later slice,
// so for now it only says so.
function AddExpenseButton() {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Add expense"
      onPress={() =>
        Alert.alert('Add expense', 'Adding expenses is coming soon.')
      }
      style={styles.fab}
    >
      <Text style={styles.fabText}>+</Text>
    </Pressable>
  );
}

function AppTabBar(props: BottomTabBarProps) {
  const current = props.state.routes[props.state.index].name;
  return (
    <View>
      {current !== 'Account' ? <AddExpenseButton /> : null}
      <BottomTabBar {...props} />
    </View>
  );
}

// Tab shell (SCR-07): Friends, Groups, Activity, Account. The last open tab is remembered.
export function TabNavigator() {
  const [initial, setInitial] = useState<keyof TabParamList | null>(null);
  useEffect(() => {
    let cancelled = false;
    loadLastTab().then(t => {
      if (!cancelled) {
        setInitial(t);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (initial === null) {
    return <LoadingView label="Loading" />;
  }
  return (
    <Tab.Navigator
      initialRouteName={initial ?? DEFAULT_TAB}
      screenOptions={{ headerShown: false }}
      screenListeners={({ route }) => ({
        focus: () => {
          saveLastTab(route.name);
        },
      })}
      tabBar={AppTabBar}
    >
      <Tab.Screen name="Friends" component={FriendsScreen} />
      <Tab.Screen name="Groups" component={GroupsScreen} />
      <Tab.Screen name="Activity" component={ActivityPlaceholder} />
      <Tab.Screen name="Account" component={AccountScreen} />
    </Tab.Navigator>
  );
}

const styles = StyleSheet.create({
  fab: {
    position: 'absolute',
    right: 16,
    top: -72,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#1b6e5a',
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 4,
  },
  fabText: { color: '#fff', fontSize: 28, lineHeight: 30 },
});
