import React, { useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, View } from 'react-native';
import { Theme, useTheme, useThemedStyles } from '../theme';
import { Text } from '../components/Text';
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
import { ActivityScreen } from '../screens/ActivityScreen';
import { formatBadge } from '../activity/badge';
import { useUnreadCount } from '../activity/useUnreadBadge';
import { LoadingView } from '../components/StateViews';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { TabIcon } from './TabIcons';
import { useGatedNavigate } from '../premium/gate';

type IconProps = { color: string; focused: boolean };
const friendsIcon = (p: IconProps) => <TabIcon name="Friends" {...p} />;
const groupsIcon = (p: IconProps) => <TabIcon name="Groups" {...p} />;
const activityIcon = (p: IconProps) => <TabIcon name="Activity" {...p} />;
const accountIcon = (p: IconProps) => <TabIcon name="Account" {...p} />;

const Tab = createBottomTabNavigator<TabParamList>();

// SCR-07 add-expense button. The expense form (SCR-22) ships in a later slice,
// so for now it only says so.
function AddExpenseButton() {
  const styles = useThemedStyles(makeStyles);
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

// SCR-07 search entry (F-47): a free user is sent to the paywall.
function SearchButton() {
  const styles = useThemedStyles(makeStyles);
  const gated = useGatedNavigate();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Search expenses"
      onPress={() => gated('Search', undefined)}
      style={styles.search}
    >
      <Text style={styles.searchText}>Search</Text>
    </Pressable>
  );
}

function AppTabBar(props: BottomTabBarProps) {
  const current = props.state.routes[props.state.index].name;
  return (
    <View>
      {current !== 'Account' ? <SearchButton /> : null}
      {current !== 'Account' ? <AddExpenseButton /> : null}
      <BottomTabBar {...props} />
    </View>
  );
}

// Tab shell (SCR-07): Friends, Groups, Activity, Account. The last open tab is remembered.
export function TabNavigator() {
  const { colors, isDark, layout } = useTheme();
  const insets = useSafeAreaInsets();
  const unread = useUnreadCount();
  const badge = formatBadge(unread);
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
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brand,
        tabBarInactiveTintColor: colors.textSecondary,
        tabBarShowLabel: true,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: isDark ? 0 : StyleSheet.hairlineWidth,
          height: layout.tabBarHeight + insets.bottom,
        },
        // Tab content never starts under the status bar.
        sceneStyle: {
          paddingTop: insets.top,
          backgroundColor: colors.background,
        },
      }}
      screenListeners={({ route }) => ({
        focus: () => {
          saveLastTab(route.name);
        },
      })}
      tabBar={AppTabBar}
    >
      <Tab.Screen
        name="Friends"
        component={FriendsScreen}
        options={{
          tabBarAccessibilityLabel: 'Friends',
          tabBarIcon: friendsIcon,
        }}
      />
      <Tab.Screen
        name="Groups"
        component={GroupsScreen}
        options={{
          tabBarAccessibilityLabel: 'Groups',
          tabBarIcon: groupsIcon,
        }}
      />
      <Tab.Screen
        name="Activity"
        component={ActivityScreen}
        options={{
          tabBarAccessibilityLabel: badge
            ? `Activity, ${unread} unread`
            : 'Activity',
          tabBarIcon: activityIcon,
          tabBarBadge: badge,
          // Neutral pill (design_system 6.7): not brand, not error.
          tabBarBadgeStyle: {
            backgroundColor: colors.inverseSurface,
            color: colors.inverseText,
          },
        }}
      />
      <Tab.Screen
        name="Account"
        component={AccountScreen}
        options={{
          tabBarAccessibilityLabel: 'Account',
          tabBarIcon: accountIcon,
        }}
      />
    </Tab.Navigator>
  );
}

const makeStyles = ({ colors, spacing, layout, radius, touchTarget }: Theme) =>
  StyleSheet.create({
    search: {
      position: 'absolute',
      left: spacing.lg,
      top: -(layout.fabSize + spacing.lg),
      minHeight: touchTarget.min,
      paddingHorizontal: spacing.lg,
      borderRadius: radius.pill,
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.borderStrong,
      alignItems: 'center',
      justifyContent: 'center',
      elevation: 2,
    },
    searchText: { color: colors.brandText },
    fab: {
      position: 'absolute',
      right: spacing.lg,
      top: -(layout.fabSize + spacing.lg),
      width: layout.fabSize,
      height: layout.fabSize,
      borderRadius: layout.fabSize / 2,
      backgroundColor: colors.brand,
      alignItems: 'center',
      justifyContent: 'center',
      elevation: 4,
    },
    fabText: { color: colors.textOnBrand, fontSize: 28, lineHeight: 30 },
  });
