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

test('upload accepts real .xlsx filenames and validates detected month using the shipped regexes', async () => {
  const response = await worker.fetch(new Request(base + '/app.js'), {});
  const source = await response.text();
  const extension = source.match(/file=chosen\[k\];if\(!((?:\/(?:\\.|[^/])+\/[a-z]*))\.test\(file\.name\)/);
  assert(extension, 'Upload file extension guard is present');
  const actualExtension = Function('"use strict"; return (' + extension[1] + ')')();
  assert(actualExtension.test('Daily Reporting Sheet_Saint Eyewear Pty Ltd_SEPTEMBER-2026 (1).xlsx'));
  assert(actualExtension.test('Saint_Eyewear_Pty_Ltd_-_Monthly_comparison (2).XLSX'));
  assert(!actualExtension.test('malicious.xlsx.zip'));
  const month = source.match(/if\(!((?:\/(?:\\.|[^/])+\/[a-z]*))\.test\(month\)/);
  assert(month, 'Month detection guard is present');
  const actualMonth = Function('"use strict"; return (' + month[1] + ')')();
  assert(actualMonth.test('2026-09'));
  assert(!actualMonth.test('2026-19'));
});
