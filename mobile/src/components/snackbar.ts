// Snackbar store (design_system 6.10: inverseSurface, 4 s, one action max). Rendered by <SnackbarHost/>.

export const SNACKBAR_MS = 4000;

export type Snack = {
  id: number;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
};

type Listener = (snack: Snack | null) => void;

let seq = 0;
let current: Snack | null = null;
const listeners = new Set<Listener>();

const emit = () => listeners.forEach(l => l(current));

export function showSnackbar(
  message: string,
  action?: { label: string; onPress: () => void },
): void {
  seq += 1;
  current = {
    id: seq,
    message,
    actionLabel: action?.label,
    onAction: action?.onPress,
  };
  emit();
}

export function dismissSnackbar(): void {
  current = null;
  emit();
}

export function subscribeSnackbar(listener: Listener): () => void {
  listeners.add(listener);
  listener(current);
  return () => {
    listeners.delete(listener);
  };
}
