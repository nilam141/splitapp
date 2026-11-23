import React, { useState } from 'react';
import { StatusBar } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import {
  DarkTheme,
  DefaultTheme,
  NavigationContainer,
  NavigationContainerRef,
  useNavigationContainerRef,
  Theme as NavigationTheme,
} from '@react-navigation/native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './src/auth/AuthContext';
import { createAppQueryClient } from './src/offline/queryClient';
import { LinkHandler } from './src/links/LinkHandler';
import type { RootStackParamList } from './src/navigation/types';
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
  onReady,
  children,
}: {
  navigationRef: React.RefObject<NavigationContainerRef<RootStackParamList> | null>;
  onReady: () => void;
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
      <NavigationContainer
        ref={
          navigationRef as unknown as React.Ref<
            NavigationContainerRef<ReactNavigation.RootParamList>
          >
        }
        theme={navTheme}
        onReady={onReady}
      >
        {children}
      </NavigationContainer>
    </>
  );
}

export default function App({
  queryClient: injected,
  navigationRef,
}: Props = {}) {
  const [created] = useState(() => createAppQueryClient());
  const queryClient = injected ?? created;
  const internalRef = useNavigationContainerRef<RootStackParamList>();
  const ref = (navigationRef ??
    internalRef) as React.RefObject<NavigationContainerRef<RootStackParamList> | null>;
  const [ready, setReady] = useState(false);
  return (
    <ThemeProvider>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <ThemedNavigation navigationRef={ref} onReady={() => setReady(true)}>
            <AuthProvider>
              <LinkHandler navigationRef={ref} ready={ready} />
              <RootNavigator />
            </AuthProvider>
          </ThemedNavigation>
        </QueryClientProvider>
      </SafeAreaProvider>
    </ThemeProvider>
  );
}
