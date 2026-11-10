import React, { useState } from 'react';
import { StatusBar } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import {
  NavigationContainer,
  NavigationContainerRef,
} from '@react-navigation/native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './src/auth/AuthContext';
import { RootNavigator } from './src/navigation/RootNavigator';

type Props = {
  queryClient?: QueryClient;
  /** Lets tests drive navigation (back) without native header buttons. */
  navigationRef?: React.RefObject<NavigationContainerRef<ReactNavigation.RootParamList> | null>;
};

export default function App({
  queryClient: injected,
  navigationRef,
}: Props = {}) {
  const [created] = useState(() => new QueryClient());
  const queryClient = injected ?? created;
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <StatusBar barStyle="dark-content" />
        <NavigationContainer ref={navigationRef}>
          <AuthProvider>
            <RootNavigator />
          </AuthProvider>
        </NavigationContainer>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
