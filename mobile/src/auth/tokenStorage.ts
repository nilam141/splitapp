import * as Keychain from 'react-native-keychain';

// Tokens live in the Android Keystore-backed secure store, never in AsyncStorage.
const SERVICE = 'splitapp.session';

export type StoredTokens = { accessToken: string; refreshToken: string };

let cached: StoredTokens | null = null;
let loaded = false;

export async function saveTokens(tokens: StoredTokens): Promise<void> {
  await Keychain.setGenericPassword('session', JSON.stringify(tokens), {
    service: SERVICE,
  });
  cached = tokens;
  loaded = true;
}

export async function loadTokens(): Promise<StoredTokens | null> {
  if (loaded) {
    return cached;
  }
  const entry = await Keychain.getGenericPassword({ service: SERVICE });
  cached = entry ? (JSON.parse(entry.password) as StoredTokens) : null;
  loaded = true;
  return cached;
}

export async function clearTokens(): Promise<void> {
  await Keychain.resetGenericPassword({ service: SERVICE });
  cached = null;
  loaded = true;
}

export async function getAccessToken(): Promise<string | null> {
  return (await loadTokens())?.accessToken ?? null;
}

/** Drops the in-memory copy so the next read goes to the keychain (simulates an app restart; used by tests). */
export function resetTokenCache(): void {
  cached = null;
  loaded = false;
}
