import fs from 'node:fs/promises';
import openapiTS, { astToString } from 'openapi-typescript';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import standalone from 'ajv/dist/standalone/index.js';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { _ } from 'ajv/dist/compile/codegen/index.js';

const root = new URL('../../../', import.meta.url);
const api = JSON.parse(await fs.readFile(new URL('packages/contracts/openapi/storage-console-v1.json', root), 'utf8'));
const paths = Object.fromEntries(Object.entries(api.paths).filter(([, path]) =>
  path.get?.tags?.includes('read') || Object.values(path).some(operation =>
    operation.tags?.some(tag => ['authentication', 'source-management'].includes(tag)))));
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
// Use this Ajv instance's Code class even when npm places formats under another copy.
const ajv = new Ajv2020({ code: { source: true, formats: _`require("ajv-formats/dist/formats").fullFormats` }, strict: true });
addFormats(ajv);
ajv.addSchema({ ...JSON.parse(validation), $id: 'storage-console-read' });
const responses = ['Overview', 'Domains', 'Source', 'Freshness', 'Page_Source_', 'Page_Volume_', 'Page_Share_', 'UserResponse',
  'SourceRegistration', 'CollectorView', 'CollectorCredential', 'Page_CollectorView_'];
const compiled = standalone(ajv, Object.fromEntries(responses.map(name => [name, `storage-console-read#/$defs/${name}`])));
const bundled = await build({ stdin: { contents: compiled, resolveDir: fileURLToPath(new URL('../', import.meta.url)) }, bundle: true, platform: 'browser', format: 'esm', minify: true, write: false });
const declarations = `declare const validators: Record<${responses.map(name => JSON.stringify(name)).join(' | ')}, (value: unknown) => boolean>;\nexport default validators;\n`;
for (const [path, contents] of [['src/api/generated.ts', types], ['src/api/schemas.json', validation], ['src/api/validators.generated.mjs', bundled.outputFiles[0].text], ['src/api/validators.generated.d.mts', declarations]]) {
  const target = new URL(path, new URL('../', import.meta.url));
  if (process.argv.includes('--check')) {
    if (await fs.readFile(target, 'utf8') !== contents) throw new Error('API_CONTRACT_DRIFT');
  } else {
    await fs.mkdir(new URL('./', target), { recursive: true });
    await fs.writeFile(target, contents);
  }
}
