import { expect, test } from 'vitest';
import validators from './validators.generated.mjs';

const collector = {
  id: '00000000-0000-4000-8000-000000000001',
  source_node_id: '00000000-0000-4000-8000-000000000002',
  collector_type: 'WINDOWS', version: null, enabled: true,
  created_at: '2026-01-01T00:00:00Z', last_seen_at: null,
};

test('generated collector metadata validator forbids credentials and unknown fields', () => {
  expect(validators.CollectorView(collector)).toBe(true);
  expect(validators.CollectorView({ ...collector, token: 't'.repeat(43) })).toBe(false);
  expect(validators.CollectorView({ ...collector, token_hash: 't'.repeat(64) })).toBe(false);
  expect(validators.CollectorView({ ...collector, enabled: 'true' })).toBe(false);
  expect(validators.CollectorView({ ...collector, collector_type: 'UNSUPPORTED' })).toBe(false);
});

test('one-time response validates token shape and keeps it out of collector list', () => {
  expect(validators.CollectorCredential({ ...collector, token: 't'.repeat(43) })).toBe(true);
  for (const token of ['', 't'.repeat(42), 't'.repeat(44), '?'.repeat(43)]) {
    expect(validators.CollectorCredential({ ...collector, token })).toBe(false);
  }
  const page = { items: [collector], limit: 50, offset: 0, total: 1 };
  expect(validators.Page_CollectorView_(page)).toBe(true);
  expect(validators.Page_CollectorView_({ ...page, items: [{ ...collector, token: 't'.repeat(43) }] })).toBe(false);
});

test('source registration response rejects unbounded cadence and leaked fields', () => {
  const source = { id: collector.source_node_id, source_type: 'FILESERVER', hostname: 'synthetic',
    fqdn: null, instance_id: 'immutable', expected_cadence_seconds: 60,
    created_at: '2026-01-01T00:00:00Z' };
  expect(validators.SourceRegistration(source)).toBe(true);
  expect(validators.SourceRegistration({ ...source, expected_cadence_seconds: 86401 })).toBe(false);
  expect(validators.SourceRegistration({ ...source, expected_cadence_seconds: true })).toBe(false);
  expect(validators.SourceRegistration({ ...source, token_hash: 'forbidden' })).toBe(false);
});
