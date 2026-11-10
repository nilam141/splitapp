import Contacts from 'react-native-contacts';
import { isE164, isEmail, normalizePhone } from './validation';

export type DeviceContact = {
  id: string;
  name: string;
  email?: string;
  phone_e164?: string;
};

export type ContactsPermission = 'granted' | 'denied' | 'undetermined';

const toPermission = (s: string): ContactsPermission =>
  s === 'authorized' || s === 'limited'
    ? 'granted'
    : s === 'denied'
      ? 'denied'
      : 'undetermined';

export async function checkContactsPermission(): Promise<ContactsPermission> {
  try {
    return toPermission(await Contacts.checkPermission());
  } catch {
    return 'undetermined';
  }
}

export async function requestContactsPermission(): Promise<ContactsPermission> {
  try {
    return toPermission(await Contacts.requestPermission());
  } catch {
    return 'denied';
  }
}

/** Device contacts that have a usable email or an E.164 phone number, sorted by name. */
export async function loadDeviceContacts(): Promise<DeviceContact[]> {
  const all = await Contacts.getAllWithoutPhotos();
  const out: DeviceContact[] = [];
  for (const c of all) {
    const email = c.emailAddresses.map(e => e.email.trim()).find(isEmail);
    const phone = c.phoneNumbers
      .map(p => normalizePhone(p.number))
      .find(isE164);
    const name = (c.displayName ?? c.givenName ?? '').trim();
    if (!name || (!email && !phone)) {
      continue;
    }
    out.push({
      id: c.recordID,
      name,
      email: email?.toLowerCase(),
      phone_e164: email ? undefined : phone,
    });
  }
  return out.sort((a, b) => a.name.localeCompare(b.name));
}
