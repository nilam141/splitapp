import type { QueryClient } from '@tanstack/react-query';
import type { Error as ApiError } from './generated/model';
import {
  getListExpensesUrl,
  getListFriendsUrl,
  getListGroupsUrl,
} from './generated/splitapp';

type Result = { status: number; data?: unknown };

/** The API error body, if the response carries one. */
export function apiErrorOf(res: Result): ApiError | undefined {
  const d = res.data;
  return d && typeof d === 'object' && 'code' in d
    ? (d as ApiError)
    : undefined;
}

// Client-generated key for the optional Idempotency-Key header (UUID v4 shape).
// Not a secret, only a de-duplication token, so Math.random is acceptable.
export function newIdempotencyKey(): string {
  const hex = '0123456789abcdef';
  let out = '';
  for (let i = 0; i < 36; i += 1) {
    if (i === 8 || i === 13 || i === 18 || i === 23) {
      out += '-';
    } else if (i === 14) {
      out += '4';
    } else if (i === 19) {
      out += hex[8 + Math.floor(Math.random() * 4)];
    } else {
      out += hex[Math.floor(Math.random() * 16)];
    }
  }
  return out;
}

export const idempotencyHeaders = (key: string) => ({
  headers: { 'Idempotency-Key': key },
});

// Generated query keys start with the request URL, so a prefix on the URL
// matches the list and every per-id query.
const startsWithUrl = (qc: QueryClient, url: string) =>
  qc.invalidateQueries({
    predicate: q => {
      const head = q.queryKey[0];
      return typeof head === 'string' && head.startsWith(url);
    },
  });

/** listFriends and getFriend (SCR-14: after leave/delete the former co-members must appear). */
export const invalidateFriends = (qc: QueryClient) =>
  startsWithUrl(qc, getListFriendsUrl().split('?')[0]);

/** listGroups, getGroup and everything under /groups/{id}. */
export const invalidateGroups = (qc: QueryClient) =>
  startsWithUrl(qc, getListGroupsUrl());

/** listExpenses, getExpense and its comments (everything under /expenses). */
export const invalidateExpenses = (qc: QueryClient) =>
  startsWithUrl(qc, getListExpensesUrl().split('?')[0]);
