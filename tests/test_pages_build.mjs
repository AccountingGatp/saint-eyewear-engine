import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
execFileSync(process.execPath, ['tools/build_pages.mjs'], { cwd: new URL('../', import.meta.url) });
const { default: worker } = await import('../dist/_worker.js');
const base = 'https://qa.invalid';
test('Pages bundle serves the actual React entry HTML', async () => {
  const response = await worker.fetch(new Request(base + '/'), {});
  assert.equal(response.status, 200);
  assert.match(await response.text(), /id="root"/);
  assert.match(response.headers.get('Content-Security-Policy'), /frame-ancestors 'none'/);
});
test('Pages bundle serves application JS and CSS', async () => {
  for (const path of ['/app.js', '/style.css']) {
    const response = await worker.fetch(new Request(base + path), {});
    assert.equal(response.status, 200);
    assert((await response.text()).length > 1000);
  }
});
test('Pages bundle fails closed without server bindings', async () => {
  const response = await worker.fetch(new Request(base + '/api/session'), {});
  assert.equal(response.status, 503);
});
test('Pages routes apply gateway to every request', async () => {
  const routes = JSON.parse(await readFile(new URL('../dist/_routes.json', import.meta.url), 'utf8'));
  assert.deepEqual(routes.include, ['/*']);
  assert.deepEqual(routes.exclude, []);
});
test('private source files are not served by Pages gateway', async () => {
  for (const path of ['/backend/core.py', '/edge/index.ts', '/.env', '/_worker.js']) {
    assert.equal((await worker.fetch(new Request(base + path), {})).status, 404);
  }
});
