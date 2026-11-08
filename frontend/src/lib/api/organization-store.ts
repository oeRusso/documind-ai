/**
 * The active organization (what goes in X-Organization-Id). Remembered in localStorage so a
 * reload keeps it; it is only a preference: the API checks membership on every request.
 */

const KEY = "documind.activeOrganizationId";
const listeners = new Set<() => void>();
let current: string | null | undefined;

function load(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null; // private mode or blocked storage: still works, just not remembered
  }
}

export function getActiveOrganizationId(): string | null {
  if (typeof window === "undefined") return null;
  if (current === undefined) current = load();
  return current;
}

export function setActiveOrganizationId(id: string | null): void {
  current = id;
  try {
    if (id) window.localStorage.setItem(KEY, id);
    else window.localStorage.removeItem(KEY);
  } catch {
    // ignore: see load()
  }
  listeners.forEach((listener) => listener());
}

export function subscribeActiveOrganization(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
