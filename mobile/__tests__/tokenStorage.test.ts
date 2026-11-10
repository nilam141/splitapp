describe('tokenStorage', () => {
  beforeEach(() => {
    jest.resetModules();
    jest.clearAllMocks();
  });

  const keychain = () => require('react-native-keychain');

  it('saves tokens to the keychain, not AsyncStorage', async () => {
    const { saveTokens, getAccessToken } = require('../src/auth/tokenStorage');
    await saveTokens({ accessToken: 'a', refreshToken: 'r' });
    expect(keychain().setGenericPassword).toHaveBeenCalledWith(
      'session',
      JSON.stringify({ accessToken: 'a', refreshToken: 'r' }),
      { service: 'splitapp.session' },
    );
    expect(await getAccessToken()).toBe('a');
  });

  it('restores tokens after a restart (fresh module state)', async () => {
    (keychain().getGenericPassword as jest.Mock).mockResolvedValueOnce({
      username: 'session',
      password: JSON.stringify({ accessToken: 'a2', refreshToken: 'r2' }),
    });
    const { loadTokens } = require('../src/auth/tokenStorage');
    expect(await loadTokens()).toEqual({
      accessToken: 'a2',
      refreshToken: 'r2',
    });
  });

  it('returns null when nothing is stored and after clear', async () => {
    const {
      loadTokens,
      clearTokens,
      saveTokens,
    } = require('../src/auth/tokenStorage');
    expect(await loadTokens()).toBeNull();
    await saveTokens({ accessToken: 'a', refreshToken: 'r' });
    await clearTokens();
    expect(keychain().resetGenericPassword).toHaveBeenCalled();
    expect(await loadTokens()).toBeNull();
  });
});
