import type { Error as ApiError } from '../api/generated/model';

export type AuthFormError = {
  /** Message under a specific field, if the server pointed at one. */
  field?: { name: 'email' | 'password' | 'name'; message: string };
  /** Banner-level message. */
  banner?: string;
};

type Result = { status: number; data?: unknown };

const NETWORK_MESSAGE =
  "Can't reach the server. Check your connection and try again.";

export function networkError(): AuthFormError {
  return { banner: NETWORK_MESSAGE };
}

const asApiError = (data: unknown): ApiError | undefined =>
  data && typeof data === 'object' && 'code' in data
    ? (data as ApiError)
    : undefined;

// Maps a non-success login/register response to what SCR-03/SCR-04 show.
export function mapAuthError(res: Result): AuthFormError {
  const err = asApiError(res.data);
  switch (res.status) {
    case 401:
      return { banner: 'Email or password is incorrect.' };
    case 409:
      return {
        field: { name: 'email', message: 'This email is already registered.' },
      };
    case 429:
      return { banner: 'Too many attempts. Try again in 15 minutes.' };
    case 422: {
      const fields = (
        err?.details as
          { fields?: { field: string; message: string }[] } | undefined
      )?.fields;
      const first = fields?.find(f =>
        ['email', 'password', 'name'].includes(f.field),
      );
      if (first) {
        return {
          field: {
            name: first.field as 'email' | 'password' | 'name',
            message: first.message,
          },
        };
      }
      return {
        banner: err?.message ?? 'Please check your details and try again.',
      };
    }
    default:
      return { banner: 'Something went wrong on our side. Try again shortly.' };
  }
}
