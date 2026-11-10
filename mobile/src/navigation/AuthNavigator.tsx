import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { AuthStackParamList } from './types';
import { WelcomeScreen } from '../screens/WelcomeScreen';
import { SignUpScreen } from '../screens/SignUpScreen';
import { LogInScreen } from '../screens/LogInScreen';
import { SessionExpiredScreen } from '../screens/SessionExpiredScreen';
import { useAuth } from '../auth/AuthContext';

const Stack = createNativeStackNavigator<AuthStackParamList>();

export function AuthNavigator() {
  const { expiredEmail } = useAuth();
  // SCR-44 replaces the welcome screen when a live session just ended.
  const expired = expiredEmail !== null;
  return (
    <Stack.Navigator initialRouteName={expired ? 'SessionExpired' : 'Welcome'}>
      <Stack.Screen
        name="Welcome"
        component={WelcomeScreen}
        options={{ headerShown: false }}
      />
      <Stack.Screen
        name="SessionExpired"
        component={SessionExpiredScreen}
        initialParams={{ email: expiredEmail ?? '' }}
        options={{ headerShown: false }}
      />
      <Stack.Screen
        name="SignUp"
        component={SignUpScreen}
        options={{ title: 'Sign up' }}
      />
      <Stack.Screen
        name="LogIn"
        component={LogInScreen}
        options={{ title: 'Log in' }}
      />
    </Stack.Navigator>
  );
}
