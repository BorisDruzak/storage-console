import type { components } from '../api/generated';
import validators from '../api/validators.generated.mjs';

export type Actor = components['schemas']['UserResponse'];
export type Provider = components['schemas']['LoginRequest']['provider'];
export type AuthErrorCode = 'AUTH_FAILED' | 'AUTH_UNAVAILABLE' | 'AUTH_RATE_LIMITED';
export class AuthError extends Error {
  constructor(readonly code: AuthErrorCode) { super(code); }
}

async function request(path: string, init: RequestInit): Promise<Response> {
  try {
    const response = await fetch('/api/v1/auth/' + path, {
      ...init, credentials: 'same-origin', cache: 'no-store',
      signal: init.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(10000)]) : AbortSignal.timeout(10000),
    });
    if (response.status === 429) throw new AuthError('AUTH_RATE_LIMITED');
    if (!response.ok && response.status !== 401) throw new AuthError('AUTH_UNAVAILABLE');
    return response;
  } catch (error) {
    if (error instanceof AuthError) throw error;
    throw new AuthError('AUTH_UNAVAILABLE');
  }
}

async function actor(response: Response): Promise<Actor> {
  const text = await response.text();
  if (text.length > 16384) throw new AuthError('AUTH_UNAVAILABLE');
  try {
    const value: unknown = JSON.parse(text);
    if (!validators.UserResponse(value)) throw new AuthError('AUTH_UNAVAILABLE');
    return value as Actor;
  } catch { throw new AuthError('AUTH_UNAVAILABLE'); }
}

export async function me(signal?: AbortSignal): Promise<Actor | null> {
  const response = await request('me', { method: 'GET', signal });
  return response.status === 401 ? null : actor(response);
}

export async function login(provider: Provider, username: string, password: string, signal?: AbortSignal): Promise<Actor> {
  const response = await request('login', {
    method: 'POST', signal, headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, username, password }),
  });
  if (response.status === 401) throw new AuthError('AUTH_FAILED');
  return actor(response);
}

export async function logout(signal?: AbortSignal): Promise<void> {
  const values = document.cookie.split(';').map(part => part.trim()).filter(part => part.startsWith('__Host-storage_csrf='));
  const csrf = values.length === 1 ? values[0].slice('__Host-storage_csrf='.length) : '';
  if (!/^[A-Za-z0-9_-]{43}$/.test(csrf)) throw new AuthError('AUTH_UNAVAILABLE');
  const response = await request('logout', { method: 'POST', signal, headers: { 'X-CSRF-Token': csrf } });
  if (response.status !== 204 && response.status !== 401) throw new AuthError('AUTH_UNAVAILABLE');
}
