import { useEffect, useRef, useState } from 'react';
import { ControlError, type ControlErrorCode } from './client';

export function useControlRequest(onPermissionDenied?: () => void, onUnconfirmed?: () => void) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ControlErrorCode | null>(null);
  const active = useRef<AbortController | null>(null);
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; active.current?.abort(); active.current = null; }, []);
  async function run<T>(operation: (signal: AbortSignal) => Promise<T>, success: (value: T) => void) {
    if (active.current) return;
    const controller = new AbortController(); active.current = controller;
    const version = ++generation.current; setPending(true); setError(null);
    try {
      const result = await operation(controller.signal);
      if (version === generation.current) success(result);
    } catch (failure) {
      if (version === generation.current) {
        const code = failure instanceof ControlError ? failure.code : 'CONTROL_UNAVAILABLE';
        setError(code);
        if (code === 'AUTH_FORBIDDEN') onPermissionDenied?.();
        if (code === 'CONTROL_UNAVAILABLE' || code === 'INVALID_RESPONSE' || code === 'TIMEOUT') onUnconfirmed?.();
      }
    } finally {
      if (version === generation.current) { active.current = null; setPending(false); }
    }
  }
  return { pending, error, run };
}
