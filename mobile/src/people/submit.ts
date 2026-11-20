import type { Error as ApiError, FriendCreate } from '../api/generated/model';
import { addFriend } from '../api/generated/splitapp';
import { apiErrorOf, idempotencyHeaders } from '../api/helpers';
import type { PersonDraft } from './types';

export type PersonOutcome = { key: string; error?: string };

export const friendBody = (
  p: Extract<PersonDraft, { kind: 'new' }>,
): FriendCreate => ({
  ...(p.email ? { email: p.email } : {}),
  ...(p.phone_e164 ? { phone_e164: p.phone_e164 } : {}),
  ...(p.name.trim() ? { name: p.name.trim() } : {}),
});

const messageFor = (status: number, err?: ApiError): string => {
  if (err?.code === 'CANNOT_FRIEND_SELF') {
    return "You can't add yourself.";
  }
  if (status === 422) {
    return err?.message ?? 'Check the email or phone number.';
  }
  if (status === 429) {
    return 'Too many requests. Try again shortly.';
  }
  return err?.message ?? 'Could not add this person. Try again.';
};

/** POST /friends for each new person, one at a time. 201 (new) and 200 (already friends) both count as success. */
export async function addFriends(
  people: PersonDraft[],
): Promise<PersonOutcome[]> {
  const outcomes: PersonOutcome[] = [];
  for (const p of people) {
    if (p.kind !== 'new') {
      continue;
    }
    try {
      const res = await addFriend(
        friendBody(p),
        idempotencyHeaders(p.idempotencyKey),
      );
      outcomes.push(
        res.status === 200 || res.status === 201
          ? { key: p.key }
          : { key: p.key, error: messageFor(res.status, apiErrorOf(res)) },
      );
    } catch {
      outcomes.push({
        key: p.key,
        error: "Can't reach the server. Check your connection and try again.",
      });
    }
  }
  return outcomes;
}
