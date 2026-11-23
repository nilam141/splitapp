import { useCallback } from 'react';
import { useListCurrencies } from '../api/generated/splitapp';
import { fallbackExponent, formatMoney, ExponentOf } from './format';

// Exponents come from the cached GET /currencies response (shared with the currency picker).
export function useMoney() {
  const query = useListCurrencies({
    query: { staleTime: 24 * 60 * 60 * 1000 },
  });
  const list = query.data?.status === 200 ? query.data.data : undefined;
  const exponentOf: ExponentOf = useCallback(
    (currency: string) =>
      list?.find(c => c.code === currency)?.exponent ??
      fallbackExponent(currency),
    [list],
  );
  const format = useCallback(
    (amountMinor: number, currency: string) =>
      formatMoney(amountMinor, currency, exponentOf(currency)),
    [exponentOf],
  );
  return { format, exponentOf };
}
