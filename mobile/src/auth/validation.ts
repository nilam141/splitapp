// Client-side validation mirroring SCR-03 / SCR-04. The server stays authoritative.
export type FieldErrors = Partial<
  Record<'name' | 'email' | 'password', string>
>;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

export function validateSignUp(input: {
  name: string;
  email: string;
  password: string;
}): FieldErrors {
  const errors: FieldErrors = {};
  const name = input.name.trim();
  if (name.length < 1 || name.length > 100) {
    errors.name = 'Enter your name (up to 100 characters).';
  }
  const email = normalizeEmail(input.email);
  if (!EMAIL_RE.test(email) || email.length > 254) {
    errors.email = 'Enter a valid email address.';
  }
  if (input.password.length < 8 || input.password.length > 128) {
    errors.password = 'Password must be 8 to 128 characters.';
  }
  return errors;
}

export function validateLogIn(input: {
  email: string;
  password: string;
}): FieldErrors {
  const errors: FieldErrors = {};
  if (normalizeEmail(input.email).length === 0) {
    errors.email = 'Enter your email.';
  }
  if (input.password.length === 0) {
    errors.password = 'Enter your password.';
  }
  return errors;
}
