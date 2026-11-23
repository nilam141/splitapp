/**
 * S6-Q-2 finding (BUG, found on the emulator): the persisted cache (S6-M-5) is saved with JSON.stringify, which turns
 * the first-page param `undefined` of every useInfiniteQuery into `null`. After a cold start the stale query is
 * refetched with `pageParam = null`, and the screens pass `cursor: pageParam` to the API, which sends `cursor=null`:
 * the server answers 422 and the group timeline shows "Something went wrong" (seen on API 36:
 * `GET /groups/{id}/timeline?limit=30&cursor=null` -> 422). Same pattern in GroupDetail, FriendDetail,
 * ExpenseDetail comments and Search. This test fails until the first page is requested without a cursor again.
 */
import { QueryClient, dehydrate, hydrate } from '@tanstack/react-query';
import { cursorOf } from '../../src/api/helpers';

type Page = { items: string[]; next_cursor: string | null };

const KEY = ['group-timeline', 'g1'];

function options(seen: unknown[]) {
  return {
    queryKey: KEY,
    queryFn: async ({ pageParam }: { pageParam: string | undefined }) => {
      // the screens build the request cursor with cursorOf(pageParam)
      seen.push(cursorOf(pageParam));
      const page: Page = { items: ['a'], next_cursor: null };
      return page;
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last: Page) => last.next_cursor ?? undefined,
    staleTime: 0,
  };
}

test('an infinite query restored from the persisted cache refetches its first page without a cursor', async () => {
  // first run: fetch, then persist exactly like src/offline/cache.ts does
  const first = new QueryClient();
  await first.fetchInfiniteQuery(options([]));
  const stored = JSON.stringify({
    state: dehydrate(first, {
      shouldDehydrateQuery: q => q.state.status === 'success',
    }),
  });

  // cold start: new client, hydrate from storage, the screen mounts and the stale query refetches
  const second = new QueryClient();
  hydrate(second, JSON.parse(stored).state);
  const seen: unknown[] = [];
  await second.fetchInfiniteQuery(options(seen));

  first.clear();
  second.clear();
  expect(seen.length).toBeGreaterThan(0);
  for (const param of seen) {
    expect(param).toBeUndefined(); // actual today: null, which the screens send as ?cursor=null
  }
});
