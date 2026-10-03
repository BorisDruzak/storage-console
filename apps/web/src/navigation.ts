import { useSyncExternalStore } from 'react';

export const sections = ['overview', 'health', 'activity', 'access', 'recovery', 'hygiene', 'diagnostics', 'discovery', 'sources', 'policies', 'settings', 'audit'] as const;
export type Section = typeof sections[number];
const subscribe = (callback: () => void) => {
  window.addEventListener('hashchange', callback);
  return () => window.removeEventListener('hashchange', callback);
};
export function useRoute() {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  const [path, search] = hash.slice(1).split('?');
  const section = sections.find(item => item === path) ?? 'overview';
  const params = new URLSearchParams(search);
  const raw = Number(params.get('offset') ?? 0);
  const offset = Number.isInteger(raw) && raw >= 0 && raw <= 1000000 ? raw : 0;
  return { section, params, offset };
}
export function link(section: Section, values: Record<string, string | number> = {}) {
  const params = new URLSearchParams(Object.entries(values).map(([key, value]) => [key, String(value)]));
  return '#' + section + (params.size ? '?' + params : '');
}
