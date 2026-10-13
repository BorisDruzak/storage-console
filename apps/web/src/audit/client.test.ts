import { afterEach, expect, test, vi } from 'vitest';
import { changeAudit } from './client';

const id = '00000000-0000-0000-0000-000000000001';
afterEach(() => vi.unstubAllGlobals());

test.each([401, 403])('cancelled old audit read cannot change a new session: %s', async status => {
  const controller = new AbortController();
  let finish!: (response: Response) => void;
  const expired = vi.fn(), changed = vi.fn();
  window.addEventListener('storage-session-expired', expired);
  window.addEventListener('storage-permission-changed', changed);
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { finish = resolve; })));
  try {
    const pending = changeAudit(id, controller.signal);
    const rejected = expect(pending).rejects.toBeDefined();
    controller.abort(); finish(new Response('{}', { status }));
    await rejected;
    expect(expired).not.toHaveBeenCalled(); expect(changed).not.toHaveBeenCalled();
  } finally {
    window.removeEventListener('storage-session-expired', expired);
    window.removeEventListener('storage-permission-changed', changed);
  }
});
