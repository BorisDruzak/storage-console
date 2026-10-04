import type { FormEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useSession } from './SessionProvider';
import type { Provider } from './client';
const providers: Provider[] = ['ldap', 'local'];

export function LoginPage() {
  const { t } = useTranslation();
  const session = useSession();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      await session.login(String(data.get('provider')) as Provider, String(data.get('username')), String(data.get('password')));
    } finally { form.reset(); }
  }
  return <main className="auth-page"><section className="auth-card">
    <h1>{t('auth.title')}</h1><p>{t('app.subtitle')}</p>
    {session.state.kind === 'anonymous' && session.state.failure ? <p role="alert">{t(`auth.${session.state.failure}`)}</p> : null}
    <form onSubmit={event => void submit(event)}>
      <label>{t('auth.provider')}<select name="provider" defaultValue={providers[0]}>{providers.map(provider => <option key={provider} value={provider}>{t(provider === 'ldap' ? 'auth.directory' : 'auth.local')}</option>)}</select></label>
      <label>{t('auth.username')}<input name="username" required maxLength={64} autoComplete="username" /></label>
      <label>{t('auth.password')}<input name="password" type="password" required maxLength={1024} autoComplete="current-password" /></label>
      <button type="submit">{t('auth.login')}</button>
    </form>
  </section></main>;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const session = useSession();
  if (session.state.kind === 'loading') return <main className="auth-page"><p role="status">{t('common.loading')}</p></main>;
  if (session.state.kind === 'error') return <main className="auth-page"><section className="auth-card"><p role="alert">{t(session.state.operation === 'logout' ? 'auth.logoutUnavailable' : 'auth.AUTH_UNAVAILABLE')}</p><button onClick={session.retry}>{t('common.retry')}</button></section></main>;
  if (session.state.kind === 'anonymous') return <LoginPage />;
  return <><div className="session-bar"><span>{session.state.actor.username}</span><button onClick={() => void session.logout()}>{t('auth.logout')}</button></div>{children}</>;
}
