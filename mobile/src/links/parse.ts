import { APP_LINK_HOST, APP_LINK_SCHEME } from '../config';

// F-54: the link kinds the app opens. Anything else is ignored (no error, the app just opens).
export type DeepLink =
  | { kind: 'join'; token: string }
  | { kind: 'reset'; token: string }
  | { kind: 'add-friend'; code: string };

const TOKEN = /^[A-Za-z0-9_-]{4,128}$/;
const SEGMENT: Record<string, DeepLink['kind']> = {
  join: 'join',
  reset: 'reset',
  add: 'add-friend',
};

/** Parses https://<host>/<join|reset|add>/<value> and <scheme>://<join|reset|add>/<value>. Returns null for anything else. */
export function parseDeepLink(url: string | null | undefined): DeepLink | null {
  if (!url) {
    return null;
  }
  const m = /^([a-z][a-z0-9+.-]*):\/\/([^?#]*)/i.exec(url.trim());
  if (!m) {
    return null;
  }
  const scheme = m[1].toLowerCase();
  const parts = m[2].split('/').filter(p => p !== '');
  if (scheme === 'https' || scheme === 'http') {
    if (parts.shift()?.toLowerCase() !== APP_LINK_HOST) {
      return null;
    }
  } else if (scheme !== APP_LINK_SCHEME) {
    return null;
  }
  const [segment, value] = parts;
  const kind = segment ? SEGMENT[segment.toLowerCase()] : undefined;
  if (!kind || !value || parts.length !== 2 || !TOKEN.test(value)) {
    return null;
  }
  if (kind === 'add-friend') {
    return { kind, code: value };
  }
  return { kind, token: value };
}
