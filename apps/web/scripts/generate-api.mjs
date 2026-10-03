import fs from 'node:fs/promises';
import openapiTS, { astToString } from 'openapi-typescript';

const root = new URL('../../../', import.meta.url);
const api = JSON.parse(await fs.readFile(new URL('packages/contracts/openapi/storage-console-v1.json', root), 'utf8'));
const paths = Object.fromEntries(Object.entries(api.paths).filter(([, path]) => path.get?.tags?.includes('read')));
const names = new Set();
function references(value) {
  if (!value || typeof value !== 'object') return;
  if (value.$ref) {
    const name = value.$ref.replace('#/components/schemas/', '');
    if (!names.has(name)) { names.add(name); references(api.components.schemas[name]); }
  }
  for (const child of Object.values(value)) references(child);
}
references(paths);
const schemas = Object.fromEntries([...names].sort().map(name => [name, api.components.schemas[name]]));
const types = astToString(await openapiTS({ ...api, paths, components: { schemas } }));
const validation = JSON.stringify({
  $schema: 'https://json-schema.org/draft/2020-12/schema',
  $defs: JSON.parse(JSON.stringify(schemas).replaceAll('#/components/schemas/', '#/$defs/')),
}, null, 2) + '\n';
for (const [path, contents] of [['src/api/generated.ts', types], ['src/api/schemas.json', validation]]) {
  const target = new URL(path, new URL('../', import.meta.url));
  if (process.argv.includes('--check')) {
    if (await fs.readFile(target, 'utf8') !== contents) throw new Error('API_CONTRACT_DRIFT');
  } else {
    await fs.mkdir(new URL('./', target), { recursive: true });
    await fs.writeFile(target, contents);
  }
}
