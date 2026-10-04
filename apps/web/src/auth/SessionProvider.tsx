import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import * as api from './client';

type State = { kind: 'loading' } | { kind: 'anonymous'; failure?: api.AuthErrorCode } |
  { kind: 'authenticated'; actor: api.Actor } | { kind: 'error'; operation: 'restore' | 'logout' };
type Session = { state: State; login: (provider: api.Provider, username: string, password: string) => Promise<void>; logout: () => Promise<void>; retry: () => void };
const Context = createContext<Session | null>(null);

export function useSession(): Session {
  const value = useContext(Context);
  if (!value) throw new Error('SESSION_PROVIDER_REQUIRED');
  return value;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const cache = useQueryClient();
  const [state, setState] = useState<State>({ kind: 'loading' });
  const generation = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const channel = useRef<BroadcastChannel | null>(null);
  const clear = useCallback(() => {
    generation.current++;
    pending.current?.abort();
    pending.current = null;
    void cache.cancelQueries({}, { silent: true });
    cache.clear();
  }, [cache]);
  const expire = useCallback((broadcast = true) => {
    clear();
    setState({ kind: 'anonymous' });
    if (broadcast) channel.current?.postMessage('expired');
  }, [clear]);
  const restore = useCallback(async () => {
    clear();
    setState({ kind: 'loading' });
    const version = generation.current;
    const controller = new AbortController();
    pending.current = controller;
    try {
      const actor = await api.me(controller.signal);
      if (version === generation.current) setState(actor ? { kind: 'authenticated', actor } : { kind: 'anonymous' });
    } catch {
      if (version === generation.current) setState({ kind: 'error', operation: 'restore' });
    }
  }, [clear]);
  const login = useCallback(async (provider: api.Provider, username: string, password: string) => {
    clear();
    setState({ kind: 'loading' });
    const version = generation.current;
    const controller = new AbortController();
    pending.current = controller;
    try {
      const actor = await api.login(provider, username, password, controller.signal);
      if (version === generation.current) {
        setState({ kind: 'authenticated', actor });
        channel.current?.postMessage('changed');
      }
    } catch (error) {
      if (version === generation.current) setState({ kind: 'anonymous', failure: error instanceof api.AuthError ? error.code : 'AUTH_UNAVAILABLE' });
    }
  }, [clear]);
  const logout = useCallback(async () => {
    clear();
    setState({ kind: 'loading' });
    channel.current?.postMessage('expired');
    const version = generation.current;
    const controller = new AbortController();
    pending.current = controller;
    try {
      await api.logout(controller.signal);
      channel.current?.postMessage('expired');
      if (version === generation.current) setState({ kind: 'anonymous' });
    } catch {
      if (version === generation.current) setState({ kind: 'error', operation: 'logout' });
    }
  }, [clear]);
  useEffect(() => {
    const expired = () => expire();
    window.addEventListener('storage-session-expired', expired);
    if (typeof BroadcastChannel !== 'undefined') {
      const connection = new BroadcastChannel('storage-console-session');
      channel.current = connection;
      connection.onmessage = event => {
        if (event.data === 'expired') expire(false);
        if (event.data === 'changed') void restore();
      };
    }
    void restore();
    return () => {
      window.removeEventListener('storage-session-expired', expired);
      channel.current?.close();
      channel.current = null;
      clear();
    };
  }, [clear, expire, restore]);
  return <Context.Provider value={{ state, login, logout, retry: () => { void (state.kind === 'error' && state.operation === 'logout' ? logout() : restore()); } }}>{children}</Context.Provider>;
}
