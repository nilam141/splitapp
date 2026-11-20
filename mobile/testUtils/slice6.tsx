/* eslint-env jest */
// Shared set-up for the Slice 6 screen tests (fake server behind fetch; the real generated client and screens run).
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createNavigationContainerRef } from '@react-navigation/native';
import { QueryClient } from '@tanstack/react-query';
import App from '../App';
import { resetTokenCache } from '../src/auth/tokenStorage';
import { setOffline } from '../src/offline/connectivity';
import { clearQueue } from '../src/offline/queue';
import { FakeServer } from './fakeServer';

export function makeEnv() {
  const env = {
    server: new FakeServer(),
    qc: new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity },
        mutations: { gcTime: Infinity },
      },
    }),
    navRef: createNavigationContainerRef(),
  };
  return env;
}

export async function resetEnv(env: ReturnType<typeof makeEnv>) {
  env.server = new FakeServer();
  env.server.seedTokens();
  env.server.install();
  env.qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { gcTime: Infinity },
    },
  });
  resetTokenCache();
  setOffline(false);
  // let writes from the previous test's unmounting app land before wiping storage
  await new Promise(r => setTimeout(r, 30));
  await AsyncStorage.clear();
  await clearQueue();
}

export const launch = (env: ReturnType<typeof makeEnv>) =>
  render(<App queryClient={env.qc} navigationRef={env.navRef} />);

export const press = async (text: string | RegExp) =>
  fireEvent.press(await screen.findByText(text));
export const pressLabel = async (label: string | RegExp) =>
  fireEvent.press(await screen.findByLabelText(label));

export const reqs = (
  server: FakeServer,
  method: string,
  path: string | RegExp,
) =>
  server.log.filter(
    r =>
      r.method === method &&
      (typeof path === 'string' ? r.path === path : path.test(r.path)),
  );
