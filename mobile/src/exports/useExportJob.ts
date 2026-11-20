import { useCallback, useEffect, useRef, useState } from 'react';
import { createExport, getExport } from '../api/generated/splitapp';
import type { Export, ExportCreate } from '../api/generated/model';
import { apiErrorOf } from '../api/helpers';

export const EXPORT_POLL_MS = 1500;
export const EXPORT_MAX_POLLS = 80;

export type ExportPhase =
  | { name: 'working' }
  | { name: 'ready'; file: Export }
  | { name: 'failed'; message: string }
  | { name: 'paywall' };

const OFFLINE = "Can't reach the server. Check your connection and try again.";

/**
 * SCR-38: starts an export (one POST) and polls GET /exports/{id} until it is ready or failed. `retry` sends a
 * new POST (exactly one) after a failure. Every poll returns a fresh download URL, so the latest one is used.
 */
export function useExportJob(body: ExportCreate) {
  const [phase, setPhase] = useState<ExportPhase>({ name: 'working' });
  const [attempt, setAttempt] = useState(0);
  const bodyRef = useRef(body);
  bodyRef.current = body;

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const fail = (message: string) =>
      alive && setPhase({ name: 'failed', message });

    const poll = async (id: string, n: number) => {
      try {
        const res = await getExport(id);
        if (!alive) {
          return;
        }
        if (res.status !== 200) {
          return fail(
            res.status === 404
              ? 'This export has expired. Start a new one.'
              : (apiErrorOf(res)?.message ?? 'Could not read the export.'),
          );
        }
        if (res.data.status === 'ready') {
          setPhase({ name: 'ready', file: res.data });
        } else if (res.data.status === 'failed') {
          fail('The export could not be created.');
        } else if (n >= EXPORT_MAX_POLLS) {
          fail('The export is taking too long. Try again.');
        } else {
          timer = setTimeout(() => poll(id, n + 1), EXPORT_POLL_MS);
        }
      } catch {
        fail(OFFLINE);
      }
    };

    (async () => {
      setPhase({ name: 'working' });
      try {
        const res = await createExport(bodyRef.current);
        if (!alive) {
          return;
        }
        if (res.status === 202) {
          if (res.data.status === 'ready') {
            setPhase({ name: 'ready', file: res.data });
          } else {
            timer = setTimeout(() => poll(res.data.id, 1), EXPORT_POLL_MS);
          }
        } else if (res.status === 402) {
          setPhase({ name: 'paywall' });
        } else {
          fail(apiErrorOf(res)?.message ?? 'Could not start the export.');
        }
      } catch {
        fail(OFFLINE);
      }
    })();

    return () => {
      alive = false;
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [attempt]);

  const retry = useCallback(() => setAttempt(a => a + 1), []);
  return { phase, retry };
}
