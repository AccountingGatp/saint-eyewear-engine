/** Build a Cloudflare Pages advanced-mode Worker without network dependencies. */
import { readFile, mkdir, writeFile, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
const root = fileURLToPath(new URL('../', import.meta.url));
const out = path.join(root, 'dist');
const read = name => readFile(path.join(root, name), 'utf8');
let worker = await read('worker/index.js');
for (const [name, filename] of [['HTML','index.html'], ['SCRIPT','app.js'], ['CSS','style.css']]) {
  const statement = `import ${name} from '../frontend/${filename}';`;
  if (!worker.includes(statement)) throw new Error(`Missing expected source import: ${name}`);
  const text = await read(`frontend/${filename}`);
  worker = worker.replace(statement, () => `const ${name} = ${JSON.stringify(text)};`);
}

// Pages does not run cron triggers. Retention remains separately configured.
worker = worker.replace('export default {', 'const gateway = {');
worker += '\nexport default { fetch(request, env, ctx) { return gateway.fetch(request, env, ctx); } };\n';
await rm(out, { recursive: true, force: true });
await mkdir(out, { recursive: true });
await writeFile(path.join(out, '_worker.js'), worker);
await writeFile(path.join(out, '_routes.json'), JSON.stringify({ version: 1, include: ['/*'], exclude: [] }, null, 2));
// Never serve the application without its security gateway.
await writeFile(path.join(out, 'index.html'), '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><title>Saint Eyewear</title><p>The secure reporting gateway must be active to use this application.</p></html>');
await writeFile(path.join(out, 'robots.txt'), 'User-agent: *\nDisallow: /\n');
const checked = spawnSync(process.execPath, ['--check', path.join(out, '_worker.js')], { stdio: 'inherit' });
if (checked.status !== 0) throw new Error('Generated Worker syntax check failed.');
console.log('Built dist/_worker.js. No credentials or financial input files included.');
