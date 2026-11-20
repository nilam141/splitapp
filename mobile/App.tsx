import React, { useState } from 'react';
import { StatusBar } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import {
  DarkTheme,
  DefaultTheme,
  NavigationContainer,
  NavigationContainerRef,
  Theme as NavigationTheme,
} from '@react-navigation/native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './src/auth/AuthContext';
import { RootNavigator } from './src/navigation/RootNavigator';
import { ThemeProvider, useTheme } from './src/theme';

type Props = {
  queryClient?: QueryClient;
  /** Lets tests drive navigation (back) without native header buttons. */
  navigationRef?: React.RefObject<NavigationContainerRef<ReactNavigation.RootParamList> | null>;
};

/** Navigation container, header and tab colors come from the design-system tokens (light and dark). */
function ThemedNavigation({
  navigationRef,
  children,
}: {
  navigationRef: Props['navigationRef'];
  children: React.ReactNode;
}) {
  const { colors, isDark } = useTheme();
  const base = isDark ? DarkTheme : DefaultTheme;
  const navTheme: NavigationTheme = {
    ...base,
    dark: isDark,
    colors: {
      primary: colors.brand,
      background: colors.background,
      card: colors.surface,
      text: colors.textPrimary,
      border: colors.border,
      notification: colors.brand,
    },
  };
  return (
    <>
      <StatusBar barStyle={isDark ? 'light-content' : 'dark-content'} />
      <NavigationContainer ref={navigationRef} theme={navTheme}>
        {children}
      </NavigationContainer>
    </>
  );
}

export default function App({
  queryClient: injected,
  navigationRef,
}: Props = {}) {
  const [created] = useState(() => new QueryClient());
  const queryClient = injected ?? created;
  return (
    <ThemeProvider>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <ThemedNavigation navigationRef={navigationRef}>
            <AuthProvider>
              <RootNavigator />
            </AuthProvider>
          </ThemedNavigation>
        </QueryClientProvider>
      </SafeAreaProvider>
    </ThemeProvider>
  );
}
