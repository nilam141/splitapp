// Tiny pub/sub so the HTTP layer can tell the UI that the session is gone
// (refresh token rejected) without importing React.
type Listener = () => void;
const listeners = new Set<Listener>();

export function onSessionExpired(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function notifySessionExpired(): void {
  listeners.forEach(l => l());
}
