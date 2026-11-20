import { formatBadge } from '../src/activity/badge';

// S5-M-2: the tab bar badge shows the count up to 99, "99+" above, and is hidden at 0 (screens.md SCR-07).
describe('formatBadge', () => {
  it.each([
    [0, undefined],
    [1, '1'],
    [9, '9'],
    [98, '98'],
    [99, '99'],
    [100, '99+'],
    [250, '99+'],
    [100000, '99+'],
  ])('%d -> %s', (count, expected) => {
    expect(formatBadge(count)).toBe(expected);
  });

  it('hides for missing or negative counts', () => {
    expect(formatBadge(undefined)).toBeUndefined();
    expect(formatBadge(null)).toBeUndefined();
    expect(formatBadge(-3)).toBeUndefined();
  });
});
