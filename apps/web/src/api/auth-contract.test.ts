import { expect, test } from 'vitest';
import validators from './validators.generated.mjs';

const actor = {
  id: '6a83a99d-247d-4e58-8c49-089c703ab42d',
  username: 'synthetic-admin',
  roles: ['storage_admin'],
};

test('user contract accepts canonical roles and excludes credentials', () => {
  expect(validators.UserResponse(actor)).toBe(true);
  for (const value of [
    { ...actor, roles: [] },
    { ...actor, roles: ['unknown'] },
    { ...actor, id: 'not-a-uuid' },
    { ...actor, token: 'synthetic-token' },
    { ...actor, credential_tag: 'synthetic-version' },
  ]) expect(validators.UserResponse(value)).toBe(false);
});
