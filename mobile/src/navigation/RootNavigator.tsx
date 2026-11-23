import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { RootStackParamList } from './types';
import { AuthNavigator } from './AuthNavigator';
import { MainNavigator } from './MainNavigator';
import { LaunchScreen } from '../screens/LaunchScreen';
import { useAuth } from '../auth/AuthContext';

const Stack = createNativeStackNavigator<RootStackParamList>();

// Auth stack when logged out, main stack (tab shell and flows) when logged in (SCR-01 router).
export function RootNavigator() {
  const { status } = useAuth();
  if (status === 'loading' || status === 'error') {
    return <LaunchScreen />;
  }
  const signedIn = status === 'signedIn';
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      {signedIn ? (
        <Stack.Screen name="Main" component={MainNavigator} />
      ) : (
        <Stack.Screen name="Auth" component={AuthNavigator} />
      )}
    </Stack.Navigator>
  );
}
