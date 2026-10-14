import { act, render, screen } from '@testing-library/react';
import { I18nextProvider } from 'react-i18next';
import { afterEach, expect, test, vi } from 'vitest';
import { createI18n } from '../i18n';
import { recordEvidence } from '../api/evidence';
import { DirectoryNames } from './DirectoryNames';

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });
const time = '2026-10-14T00:00:00Z';

test('separate current AD and client names include disabled state and no event-time claim', async () => {
  const account = { state: 'CURRENT' as const, observed_at: time, snapshot_id: '00000000-0000-0000-0000-000000000001',
    latest_attempt_state: 'COMPLETE' as const, valid_for_ms: 900000,
    provenance: 'LDAP_KERBEROS_SIGNED_SEALED' as const,
    user: { sid: 'S-1-5-21-10-20-30-1001', object_guid: '00000000-0000-0000-0000-000000000002',
      account: 'RenamedAD', upn: null, display_name: 'Тестовый сотрудник', enabled: false, primary_group_id: 513 } };
  const client = { state: 'CONFIRMED_CURRENT' as const, observed_at: time, expires_at: time,
    computer_name: 'CLIENT', ptr_name: 'client.example.test', valid_for_ms: 300000,
    provenance: 'DNS_PTR_FORWARD_AD_CURRENT' as const, event_time_confirmed: false as const };
  render(<I18nextProvider i18n={await createI18n()}><DirectoryNames account={account} client={client} /></I18nextProvider>);
  expect(screen.getByText('RenamedAD')).toBeInTheDocument();
  expect(screen.getByText('Тестовый сотрудник')).toBeInTheDocument();
  expect(screen.getByText('Учётная запись отключена')).toBeInTheDocument();
  expect(screen.getByText('CLIENT')).toBeInTheDocument();
  expect(screen.getByText('Текущая проверка DNS и AD не подтверждает имя компьютера на момент события.')).toBeInTheDocument();
});

test('cached confirmed name expires without a successful refetch', async () => {
  const i18n = await createI18n();
  vi.useFakeTimers();
  vi.spyOn(performance, 'now').mockImplementation(() => Date.now());
  const client = { state: 'CONFIRMED_CURRENT' as const, valid_for_ms: 20,
    provenance: 'DNS_PTR_FORWARD_AD_CURRENT' as const, event_time_confirmed: false as const };
  recordEvidence(client, performance.now(), 20);
  render(<I18nextProvider i18n={i18n}><DirectoryNames client={client} /></I18nextProvider>);
  expect(screen.getByText('Имя клиента подтверждено на время проверки')).toBeInTheDocument();
  act(() => { vi.advanceTimersByTime(21); });
  expect(screen.getByText('Сведения устарели')).toBeInTheDocument();
  expect(screen.queryByText('Имя клиента подтверждено на время проверки')).not.toBeInTheDocument();
});
