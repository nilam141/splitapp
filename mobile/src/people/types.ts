// A person picked in the Add people wizard (SCR-21), before anything is sent.
export type PersonDraft =
  | {
      /** An existing user (a friend); only valid for group flows. */
      kind: 'user';
      key: string;
      userId: string;
      name: string;
      email?: string | null;
    }
  | {
      /** A person identified by email or phone who may not have an account yet. */
      kind: 'new';
      key: string;
      name: string;
      email?: string;
      phone_e164?: string;
      /** Sent as Idempotency-Key on POST /friends so a retry cannot duplicate. */
      idempotencyKey: string;
    };
