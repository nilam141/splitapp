import {
  validateLogIn,
  validateSignUp,
  normalizeEmail,
} from '../src/auth/validation';
import { mapAuthError } from '../src/auth/errors';

describe('validation', () => {
  it('accepts a valid sign up', () => {
    expect(
      validateSignUp({
        name: ' Asha ',
        email: 'Asha@Example.com',
        password: 'abcd1234',
      }),
    ).toEqual({});
  });
  it('rejects bad sign up fields', () => {
    const e = validateSignUp({ name: '  ', email: 'nope', password: 'short' });
    expect(Object.keys(e).sort()).toEqual(['email', 'name', 'password']);
  });
  it('enforces length limits', () => {
    expect(
      validateSignUp({
        name: 'a'.repeat(101),
        email: 'a@b.co',
        password: 'x'.repeat(129),
      }),
    ).toEqual({
      name: expect.any(String),
      password: expect.any(String),
    });
  });
  it('login only requires non-empty values', () => {
    expect(validateLogIn({ email: '', password: '' })).toEqual({
      email: expect.any(String),
      password: expect.any(String),
    });
    expect(validateLogIn({ email: 'a', password: 'b' })).toEqual({});
  });
  it('normalizes email', () => {
    expect(normalizeEmail('  A@B.Co ')).toBe('a@b.co');
  });
});

describe('mapAuthError', () => {
  it('maps contract statuses', () => {
    expect(mapAuthError({ status: 401 }).banner).toMatch(/incorrect/);
    expect(
      mapAuthError({ status: 409, data: { code: 'EMAIL_TAKEN', message: 'x' } })
        .field?.name,
    ).toBe('email');
    expect(mapAuthError({ status: 429 }).banner).toMatch(/Too many/);
    expect(mapAuthError({ status: 500 }).banner).toBeDefined();
  });
  it('uses VALIDATION_ERROR fields', () => {
    const r = mapAuthError({
      status: 422,
      data: {
        code: 'VALIDATION_ERROR',
        message: 'bad',
        details: { fields: [{ field: 'password', message: 'too weak' }] },
      },
    });
    expect(r.field).toEqual({ name: 'password', message: 'too weak' });
  });
});
