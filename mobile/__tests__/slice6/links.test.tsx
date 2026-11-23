/**
 * S6-M-1: deep links (join, add friend, reset) including resume-after-login, notification settings SCR-34, and
 * the Blocked push registration (nothing is registered). Screen-level tests against the fake server.
 */
import { Linking } from 'react-native';
import { act, fireEvent, screen, waitFor } from '@testing-library/react-native';
import { parseDeepLink } from '../../src/links/parse';
import { launch, makeEnv, press, reqs, resetEnv } from '../../testUtils/slice6';

const env = makeEnv();
beforeEach(async () => {
  await resetEnv(env);
  openWith(null);
  addListener.mockImplementation(() => ({ remove: jest.fn() }));
});
// react-native's jest setup already mocks Linking with jest.fn(); drive those mocks directly.
const initialUrl = Linking.getInitialURL as unknown as jest.Mock;
const addListener = Linking.addEventListener as unknown as jest.Mock;
const openWith = (url: string | null) => initialUrl.mockResolvedValue(url);
afterEach(() => {
  env.qc.clear();
});

describe('parseDeepLink', () => {
  it('parses join, reset and add links on the app host and the custom scheme', () => {
    expect(parseDeepLink('https://splitapp.example/join/9QX2KD7MZP')).toEqual({
      kind: 'join',
      token: '9QX2KD7MZP',
    });
    expect(parseDeepLink('splitapp://join/9QX2KD7MZP')).toEqual({
      kind: 'join',
      token: '9QX2KD7MZP',
    });
    expect(
      parseDeepLink('https://splitapp.example/reset/pr_3b9d0c6a8f'),
    ).toEqual({
      kind: 'reset',
      token: 'pr_3b9d0c6a8f',
    });
    expect(parseDeepLink('https://splitapp.example/add/K7Q2M9XP')).toEqual({
      kind: 'add-friend',
      code: 'K7Q2M9XP',
    });
  });

  it('ignores unknown paths, other hosts, missing values and odd characters', () => {
    for (const url of [
      null,
      '',
      'https://splitapp.example/',
      'https://splitapp.example/unknown/abcd1234',
      'https://evil.example/join/9QX2KD7MZP',
      'https://splitapp.example/join',
      'https://splitapp.example/join/ab',
      'https://splitapp.example/join/abcd/extra',
      'https://splitapp.example/join/<script>',
      'otherapp://join/9QX2KD7MZP',
      'not a url',
    ]) {
      expect(parseDeepLink(url)).toBeNull();
    }
  });
});

describe('S6-M-1 deep links', () => {
  it('a join link opened while logged out lands on SCR-18 after login', async () => {
    env.server.vault = null;
    openWith('https://splitapp.example/join/9QX2KD7MZP');
    await launch(env);
    await press('Log in');
    await fireEvent.changeText(
      await screen.findByLabelText('Email'),
      'asha@example.com',
    );
    await fireEvent.changeText(screen.getByLabelText('Password'), 'secret123');
    // still logged out: the link has not opened anything yet
    expect(screen.queryByText('Join this group?')).toBeNull();
    // the form's own button is the last "Log in" (the header title is the first)
    await fireEvent.press(screen.getAllByText('Log in').slice(-1)[0]);
    expect(await screen.findByText('Join this group?')).toBeTruthy();
    expect(reqs(env.server, 'POST', '/groups/join')).toHaveLength(0);
  });

  it('a join link while signed in opens SCR-18; Join posts the token and opens the group', async () => {
    const g = env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
    env.server.overrides.push(req => {
      if (req.path === '/groups/join' && req.method === 'POST') {
        return {
          status: 200,
          body: { ...JSON.parse(JSON.stringify(g)), my_balances: [] },
        };
      }
    });
    openWith('https://splitapp.example/join/9QX2KD7MZP');
    await launch(env);
    await press('Join group');
    await waitFor(() =>
      expect(reqs(env.server, 'POST', '/groups/join')).toHaveLength(1),
    );
    expect(reqs(env.server, 'POST', '/groups/join')[0].body).toEqual({
      token: '9QX2KD7MZP',
    });
    expect(await screen.findByText('Expenses')).toBeTruthy();
  });

  it('410 shows the toast "Invite no longer valid" and goes to the tabs (SCR-07)', async () => {
    env.server.overrides.push(req =>
      req.path === '/groups/join'
        ? { status: 410, body: { code: 'GONE', message: 'gone' } }
        : undefined,
    );
    openWith('splitapp://join/9QX2KD7MZP');
    await launch(env);
    await press('Join group');
    expect(await screen.findByText('Friends')).toBeTruthy();
  });

  it('a reset link opens SCR-06; a 410 shows "link expired"', async () => {
    env.server.vault = null;
    env.server.overrides.push(req =>
      req.path === '/auth/password-reset/confirm'
        ? { status: 410, body: { code: 'GONE', message: 'gone' } }
        : undefined,
    );
    openWith('https://splitapp.example/reset/pr_3b9d0c6a8f');
    await launch(env);
    await fireEvent.changeText(
      await screen.findByLabelText('New password'),
      'newpass99',
    );
    await press('Save password');
    expect(await screen.findByText('This link has expired')).toBeTruthy();
    const sent = reqs(env.server, 'POST', '/auth/password-reset/confirm')[0];
    expect(sent.body).toEqual({
      token: 'pr_3b9d0c6a8f',
      new_password: 'newpass99',
    });
  });

  it('a short reset password is rejected locally; success signs in', async () => {
    env.server.vault = null;
    env.server.overrides.push(req =>
      req.path === '/auth/password-reset/confirm'
        ? {
            status: 200,
            body: {
              access_token: 'acc1',
              refresh_token: 'rt1',
              token_type: 'bearer',
              expires_in: 900,
              user: env.server.me,
            },
          }
        : undefined,
    );
    openWith('splitapp://reset/pr_3b9d0c6a8f');
    await launch(env);
    await fireEvent.changeText(
      await screen.findByLabelText('New password'),
      'short',
    );
    await press('Save password');
    expect(
      await screen.findByText('Password must be 8 to 128 characters.'),
    ).toBeTruthy();
    expect(
      reqs(env.server, 'POST', '/auth/password-reset/confirm'),
    ).toHaveLength(0);
    await fireEvent.changeText(
      screen.getByLabelText('New password'),
      'newpass99',
    );
    await press('Save password');
    expect(await screen.findByText('Friends')).toBeTruthy();
  });

  it('an unknown link opens the app normally with no error', async () => {
    openWith('https://splitapp.example/whatever/abcd1234');
    await launch(env);
    expect(await screen.findByText('Friends')).toBeTruthy();
    expect(screen.queryByText('Join this group?')).toBeNull();
  });

  it('a link that arrives while the app is open (url event) is handled', async () => {
    const handlers: ((e: { url: string }) => void)[] = [];
    openWith(null);
    addListener.mockImplementation(
      (_t: string, h: (e: { url: string }) => void) => {
        handlers.push(h);
        return { remove: jest.fn() };
      },
    );
    await launch(env);
    await screen.findByText('Friends');
    await act(async () => {
      handlers.forEach(h =>
        h({ url: 'https://splitapp.example/join/9QX2KD7MZP' }),
      );
    });
    expect(await screen.findByText('Join this group?')).toBeTruthy();
  });

  it('an add-friend link adds by friend code through POST /friends (no lookup request)', async () => {
    openWith('https://splitapp.example/add/K7Q2M9XP');
    env.server.overrides.push(req =>
      req.path === '/friends' && req.method === 'POST'
        ? {
            status: 201,
            body: {
              friend: {
                user: {
                  id: 'u-kiran',
                  name: 'Kiran',
                  email: null,
                  is_registered: true,
                },
                balances: [],
                breakdown: [],
                settled_up_since: null,
              },
              is_new_user: false,
            },
          }
        : undefined,
    );
    await launch(env);
    await press('Add friend');
    await waitFor(() =>
      expect(reqs(env.server, 'POST', '/friends')).toHaveLength(1),
    );
    expect(reqs(env.server, 'POST', '/friends')[0].body).toEqual({
      friend_code: 'K7Q2M9XP',
    });
    expect(env.server.log.some(r => /by-code|lookup/.test(r.path))).toBe(false);
  });
});

describe('S6-M-1 notification settings (SCR-34)', () => {
  const open = async () => {
    await launch(env);
    await press('Account');
    await press('Notifications');
  };

  it('shows the 10 switches from notification_prefs and PATCHes only the toggled key', async () => {
    env.server.me = {
      ...env.server.me,
      notification_prefs: {
        ...env.server.me.notification_prefs,
        comment_added: false,
      },
    };
    await open();
    expect(await screen.findAllByRole('switch')).toHaveLength(10);
    expect(screen.getAllByText('Not sent yet.')).toHaveLength(5);
    expect(screen.getByLabelText('Comment added').props.value).toBe(false);
    expect(screen.getByLabelText('Expense added').props.value).toBe(true);
    await fireEvent(
      screen.getByLabelText('Comment added'),
      'valueChange',
      true,
    );
    await waitFor(() => {
      const patches = reqs(env.server, 'PATCH', '/users/me');
      expect(patches).toHaveLength(1);
      expect(patches[0].body).toEqual({
        notification_prefs: { comment_added: true },
      });
    });
    await waitFor(() =>
      expect(screen.getByLabelText('Comment added').props.value).toBe(true),
    );
  });

  it('a failed toggle reverts and says so', async () => {
    env.server.overrides.push(req =>
      req.method === 'PATCH' && req.path === '/users/me'
        ? { status: 500, body: { code: 'INTERNAL_ERROR', message: 'boom' } }
        : undefined,
    );
    await open();
    await screen.findAllByRole('switch');
    await fireEvent(
      screen.getByLabelText('Reminder to settle up'),
      'valueChange',
      false,
    );
    expect(await screen.findByText('boom')).toBeTruthy();
    expect(screen.getByLabelText('Reminder to settle up').props.value).toBe(
      true,
    );
  });

  it('registers no push device (push registration is Blocked, D-C)', async () => {
    await open();
    await screen.findAllByRole('switch');
    expect(env.server.log.some(r => /device|push/.test(r.path))).toBe(false);
  });
});
