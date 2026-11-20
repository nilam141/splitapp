/**
 * S6-M-3: Remind SCR-33 (FLOW-11), invite link SCR-17, My code SCR-42 (my code only). The join screen SCR-18 is in
 * links.test.tsx. Blocked by decision D-C and therefore NOT built: join preview, friend-code lookup and scan.
 */
import { Share } from 'react-native';
import { fireEvent, screen, waitFor } from '@testing-library/react-native';
import { reminderText } from '../../src/remind/message';
import { launch, makeEnv, press, reqs, resetEnv } from '../../testUtils/slice6';

const env = makeEnv();
beforeEach(async () => {
  await resetEnv(env);
});
afterEach(() => env.qc.clear());

describe('reminderText', () => {
  it('holds the formatted amount, or a plain nudge without one', () => {
    expect(reminderText('Ravi', 'INR 25.00')).toContain('INR 25.00');
    expect(reminderText('Ravi', undefined)).not.toMatch(/\d/);
    expect(reminderText('Ravi', undefined)).toContain('Ravi');
  });
});

describe('S6-M-3 Remind (SCR-33), FLOW-11', () => {
  const openRemind = async () => {
    env.server.overrides.push(req =>
      req.path === '/reminders' && req.method === 'POST'
        ? { status: 202 }
        : undefined,
    );
    env.server.addFriendRow('u-ravi', 'Ravi', [
      { amount_minor: 2500, currency: 'INR' },
    ]);
    await launch(env);
    await press('Friends');
    await press('Ravi');
    await press(/Remind about/);
    return screen.findByLabelText('Message');
  };

  it('B owes A 25.00: the message is prefilled with the amount; Send via app posts and toasts "Reminder sent"', async () => {
    const field = await openRemind();
    expect(field.props.value).toContain('25.00');
    await press('Send via app');
    await waitFor(() =>
      expect(reqs(env.server, 'POST', '/reminders')).toHaveLength(1),
    );
    expect(reqs(env.server, 'POST', '/reminders')[0].body).toMatchObject({
      to_user_id: 'u-ravi',
      group_id: null,
    });
    expect(reqs(env.server, 'POST', '/reminders')[0].body.message).toContain(
      '25.00',
    );
    expect(await screen.findByText('Reminder sent')).toBeTruthy();
    // back on the friend screen
    expect(await screen.findByText('Settle up')).toBeTruthy();
  });

  it('a second send inside a minute shows "wait 1 minute" and stays on the screen', async () => {
    let n = 0;
    env.server.overrides.push(req => {
      if (req.path === '/reminders' && req.method === 'POST') {
        n += 1;
        return n === 1
          ? { status: 202 }
          : {
              status: 429,
              body: { code: 'RATE_LIMITED', message: 'slow down' },
            };
      }
    });
    await openRemind();
    await press('Send via app');
    await screen.findByText('Reminder sent');
    await press(/Remind about/);
    await press('Send via app');
    expect(await screen.findByText(/Wait 1 minute/)).toBeTruthy();
    expect(screen.getByLabelText('Message')).toBeTruthy();
    expect(reqs(env.server, 'POST', '/reminders')).toHaveLength(2);
  });

  it('Share opens the share sheet with the text and sends no server request', async () => {
    const share = jest
      .spyOn(Share, 'share')
      .mockResolvedValue({ action: 'sharedAction' } as never);
    const field = await openRemind();
    await press('Share');
    expect(share).toHaveBeenCalledWith({ message: field.props.value });
    expect(reqs(env.server, 'POST', '/reminders')).toHaveLength(0);
    share.mockRestore();
  });

  it('a message over 1000 characters cannot be sent', async () => {
    await openRemind();
    await fireEvent.changeText(
      screen.getByLabelText('Message'),
      'x'.repeat(1001),
    );
    expect(await screen.findByText(/at most 1000 characters/)).toBeTruthy();
    await press('Send via app');
    expect(reqs(env.server, 'POST', '/reminders')).toHaveLength(0);
  });

  it('offline: shows a message, nothing is queued', async () => {
    await openRemind();
    (global as any).fetch = jest.fn(async () => {
      throw new TypeError('Network request failed');
    });
    await press('Send via app');
    expect(await screen.findByText(/Can't reach the server/)).toBeTruthy();
  });

  it('a friend who owes nothing (or whom I owe) has no Remind button', async () => {
    env.server.addFriendRow('u-ravi', 'Ravi', [
      { amount_minor: -2500, currency: 'INR' },
    ]);
    await launch(env);
    await press('Friends');
    await press('Ravi');
    await screen.findByText('Settle up');
    expect(screen.queryByText(/Remind about/)).toBeNull();
  });

  it('group balances: Remind appears only on a suggested payment owed to me', async () => {
    const g = env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
    env.server.overrides.push(req =>
      req.path === `/groups/${g.id}/balances`
        ? {
            status: 200,
            body: {
              group_id: g.id,
              simplified: true,
              members: [
                {
                  user_id: 'u-me',
                  balances: [{ amount_minor: 3333, currency: 'INR' }],
                },
                {
                  user_id: 'u-ravi',
                  balances: [{ amount_minor: -3333, currency: 'INR' }],
                },
              ],
              transfers: [
                {
                  from_user_id: 'u-ravi',
                  to_user_id: 'u-me',
                  amount_minor: 3333,
                  currency: 'INR',
                },
              ],
            },
          }
        : undefined,
    );
    await launch(env);
    await press('Groups');
    await press('Flat');
    await press('Balances');
    await press('Remind Ravi');
    expect((await screen.findByLabelText('Message')).props.value).toContain(
      '33.33',
    );
    await press('Send via app');
    await waitFor(() =>
      expect(reqs(env.server, 'POST', '/reminders')).toHaveLength(1),
    );
    expect(reqs(env.server, 'POST', '/reminders')[0].body.group_id).toBe(g.id);
  });
});

describe('S6-M-3 invite link (SCR-17)', () => {
  const open = async () => {
    env.server.addGroup('Flat', [env.server.user('u-ravi', 'Ravi')]);
    await launch(env);
    await press('Groups');
    await press('Flat');
    await press('Settings');
    await press('Invite via link');
  };
  let current = 'https://splitapp.example/join/AAAA1111';
  beforeEach(() => {
    current = 'https://splitapp.example/join/AAAA1111';
    env.server.overrides.push(req => {
      if (/\/groups\/[^/]+\/invite-link$/.test(req.path)) {
        if (req.method === 'POST') {
          current = 'https://splitapp.example/join/BBBB2222';
          return { status: 201, body: { token: 'BBBB2222', url: current } };
        }
        return { status: 200, body: { token: 'AAAA1111', url: current } };
      }
    });
  });

  it('shows the link and the warning; Share sends the link to the share sheet', async () => {
    const share = jest
      .spyOn(Share, 'share')
      .mockResolvedValue({ action: 'sharedAction' } as never);
    await open();
    expect(await screen.findByText(current)).toBeTruthy();
    expect(screen.getByText(/Anyone with the link can join/)).toBeTruthy();
    await press('Share');
    expect(share).toHaveBeenCalledWith({ message: current });
    share.mockRestore();
  });

  it('Reset asks first, then POSTs and shows the new link', async () => {
    await open();
    await screen.findByText(/AAAA1111/);
    await press('Reset link');
    expect(reqs(env.server, 'POST', /invite-link$/)).toHaveLength(0);
    await press('Reset');
    expect(await screen.findByText(/BBBB2222/)).toBeTruthy();
    expect(reqs(env.server, 'POST', /invite-link$/)).toHaveLength(1);
  });

  it('Cancel on the reset dialog sends nothing', async () => {
    await open();
    await screen.findByText(/AAAA1111/);
    await press('Reset link');
    await press('Cancel');
    expect(reqs(env.server, 'POST', /invite-link$/)).toHaveLength(0);
  });

  it('loading is shown while the link is fetched; a failure shows Retry', async () => {
    env.server.overrides.unshift(req =>
      /invite-link$/.test(req.path) && req.method === 'GET'
        ? { status: 500, body: { code: 'INTERNAL_ERROR', message: 'boom' } }
        : undefined,
    );
    await open();
    expect(await screen.findByText('Retry')).toBeTruthy();
    expect(screen.getByText(/Something went wrong/)).toBeTruthy();
  });
});

describe('S6-M-3 My code (SCR-42, my code only)', () => {
  it('shows the friend code from /users/me and shares it; there is no scan or lookup', async () => {
    const share = jest
      .spyOn(Share, 'share')
      .mockResolvedValue({ action: 'sharedAction' } as never);
    await launch(env);
    await press('Account');
    await press('My friend code');
    expect(await screen.findByText('K7Q2M9XP')).toBeTruthy();
    await press('Share code');
    expect(share).toHaveBeenCalledWith({ message: 'K7Q2M9XP' });
    expect(screen.queryByText(/Scan/i)).toBeNull();
    expect(env.server.log.some(r => /by-code|lookup|scan/i.test(r.path))).toBe(
      false,
    );
    share.mockRestore();
  });
});
