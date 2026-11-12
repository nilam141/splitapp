const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const E164_RE = /^\+[1-9][0-9]{6,14}$/;

export type Contact = { email?: string; phone_e164?: string };
export type ContactResult =
  { ok: true; value: Contact } | { ok: false; error: string };

export const CONTACT_ERROR =
  'Enter a valid email address, or a phone number with country code (for example +919876543210).';

/** Strips the spaces, dashes and brackets people type into phone numbers. */
export function normalizePhone(input: string): string {
  return input.replace(/[\s\-().]/g, '');
}

export function isEmail(input: string): boolean {
  const e = input.trim();
  return e.length <= 254 && EMAIL_RE.test(e);
}

export function isE164(input: string): boolean {
  return E164_RE.test(normalizePhone(input));
}

/** Input with an "@" is an email, anything else is a phone number. The server stays authoritative. */
export function parseContact(input: string): ContactResult {
  const text = input.trim();
  if (text.includes('@')) {
    return isEmail(text)
      ? { ok: true, value: { email: text.toLowerCase() } }
      : { ok: false, error: CONTACT_ERROR };
  }
  const phone = normalizePhone(text);
  return E164_RE.test(phone)
    ? { ok: true, value: { phone_e164: phone } }
    : { ok: false, error: CONTACT_ERROR };
}

export function validateName(name: string, required: boolean): string | null {
  const n = name.trim();
  if (n.length > 100) {
    return 'Name can be at most 100 characters.';
  }
  if (required && n.length === 0) {
    return 'Enter a name.';
  }
  return null;
}
