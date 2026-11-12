import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react-native';
import App from '../App';
import { NavigationContainer } from '@react-navigation/native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../src/auth/AuthContext';
import { TabNavigator } from '../src/navigation/TabNavigator';

const qc = new QueryClient();
afterEach(() => qc.clear());

describe('navigation shell', () => {
  it('starts on the welcome screen when logged out', async () => {
    await render(<App queryClient={qc} />);
    expect(await screen.findByText('Share expenses, settle up.')).toBeTruthy();
  });

  it('navigates from welcome to log in', async () => {
    await render(<App queryClient={qc} />);
    await fireEvent.press(await screen.findByText('Log in'));
    expect(await screen.findAllByText('Log in')).not.toHaveLength(0);
  });

  it('renders the four tabs', async () => {
    await render(
      <QueryClientProvider client={qc}>
        <AuthProvider>
          <NavigationContainer>
            <TabNavigator />
          </NavigationContainer>
        </AuthProvider>
      </QueryClientProvider>,
    );
    for (const name of ['Friends', 'Groups', 'Activity', 'Account']) {
      expect((await screen.findAllByText(name)).length).toBeGreaterThan(0);
    }
  });
});
