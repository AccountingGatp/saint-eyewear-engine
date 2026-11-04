import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
let source=await readFile(new URL('../worker/index.js',import.meta.url),'utf8');
source=source.replace(/^import HTML.*;$/m,"const HTML='<html>synthetic fixture</html>'; ").replace(/^import SCRIPT.*;$/m,"const SCRIPT='';").replace(/^import CSS.*;$/m,"const CSS='';");
const {default:worker}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const origin='https://qa.invalid';
const env={GATEWAY_SECRET:'local-test-placeholder',ENGINE:{fetch:async()=>Response.json({version:'qa',capabilities:['inspect','parse','assess','generate'],client_ready:false})}};
function req(path,{method='GET',body,cookie,originHeader=origin}={}){return new Request(origin+path,{method,headers:{...(method==='POST'?{Origin:originHeader,'Content-Type':'application/json'}:{}),...(cookie?{Cookie:cookie}:{})},...(method==='POST'?{body:JSON.stringify(body||{})}:{})});}
test('static response has noindex, nosniff and restrictive CSP',async()=>{const r=await worker.fetch(req('/'),env);assert.equal(r.status,200);assert.match(r.headers.get('X-Robots-Tag'),/noindex/);assert.match(r.headers.get('Content-Security-Policy'),/frame-ancestors 'none'/);});
test('API requires configured secure services',async()=>assert.equal((await worker.fetch(req('/api/session'),{})).status,503));
test('cross-site write is rejected before network access',async()=>assert.equal((await worker.fetch(req('/api/review',{method:'POST',originHeader:'https://evil.invalid'}),env)).status,403));
test('API rejects unsupported methods',async()=>assert.equal((await worker.fetch(req('/api/health',{method:'DELETE'}),env)).status,405));
test('no authentication yields 401 rather than demo history',async()=>{const r=await worker.fetch(req('/api/session'),env);assert.equal(r.status,401);assert.match(r.headers.get('set-cookie'),/HttpOnly/);});
test('internal completion endpoint is not browser-routable',async()=>{const r=await worker.fetch(req('/api/complete',{method:'POST',cookie:'sa_access=synthetic',body:{result:{client_ready:true}}}),env);assert.equal(r.status,404);});
test('sign-in rejects non-company email locally',async()=>{const r=await worker.fetch(req('/api/auth/signin',{method:'POST',body:{email:'other@example.invalid',password:'synthetic-only'}}),env);assert.equal(r.status,400);});
test('health cannot certify client reporting readiness',async()=>{const original=globalThis.fetch;globalThis.fetch=async()=>Response.json({database:true,storage_private:true});try{const r=await worker.fetch(req('/api/health'),env);assert.equal(r.status,200);const d=await r.json();assert.equal(d.client_ready,false);assert.equal(d.mode,'internal_review');}finally{globalThis.fetch=original}});
test('processing parses each workbook separately and assesses verified server-stored inputs',async()=>{
 const original=globalThis.fetch;const seen=[];const called=[];
 globalThis.fetch=async(url,options)=>{
  const b=JSON.parse(options.body);seen.push(b);
  if(b.action==='prepare')return Response.json({version:3,payload:{month:'2026-09',marker:'server-input',files:{pnl:'first',bs:'second',gl:'third',drs:'fourth'}}});
  if(b.action==='complete')return Response.json({saved:true});
  throw Error('Unexpected mock action '+b.action);
 };
 const e={...env,ENGINE:{fetch:async r=>{
  const p=new URL(r.url).pathname;called.push(p);
  if(p==='/inspect')return Response.json({month:'2026-09',source_map:{pnl:'bs',bs:'gl',gl:'drs',drs:'pnl'}});
  const b=await r.json();
  if(p==='/parse'){
   const expected={pnl:'second',bs:'third',gl:'fourth',drs:'first'};
   assert.equal(b.file,expected[b.kind]);assert.equal(b.month,'2026-09');
   return Response.json({kind:b.kind,data:{verified:true},source_hash:'synthetic-'+b.kind});
  }
  if(p==='/assess'){
   assert.deepEqual(Object.keys(b.parts).sort(),['bs','drs','gl','pnl']);
   assert.equal(b.parts.bs.source_hash,'synthetic-bs');
   assert.equal(b.month,'2026-09');
   assert.equal(b.client_ready,undefined);
   return Response.json({month:'2026-09',client_ready:false,flags:[],status:'review'});
  }
  throw Error('Unexpected Python endpoint '+p);
 }}};
 try{
  const r=await worker.fetch(req('/api/process',{method:'POST',cookie:'sa_access=synthetic',body:{run_id:'test-run',version:2,figures:{net:'999999'},client_ready:true}}),e);
  assert.equal(r.status,200);
  assert.deepEqual(called,['/inspect','/parse','/parse','/parse','/parse','/assess']);
  assert.equal(seen[1].action,'complete');assert.equal(seen[1].result.client_ready,false);
  assert.equal(seen[1].version,3);assert(!seen.some(x=>x.action==='detected'));
 }finally{globalThis.fetch=original}
});
test('isolated parse error identifies offending workbook and prevents approval',async()=>{
 const original=globalThis.fetch;const seen=[];
 globalThis.fetch=async(url,options)=>{
  const b=JSON.parse(options.body);seen.push(b);
  if(b.action==='prepare')return Response.json({version:3,payload:{month:'2026-08',files:{pnl:'p',bs:'b',gl:'g',drs:'d'}}});
  if(b.action==='fail')return Response.json({saved:true});
  throw Error('Unexpected workspace action');
 };
 const e={...env,ENGINE:{fetch:async r=>{
  const p=new URL(r.url).pathname;
  if(p==='/inspect')return Response.json({month:'2026-08',source_map:{pnl:'pnl',bs:'bs',gl:'gl',drs:'drs'}});
  if(p==='/parse'){
   const b=await r.json();
   if(b.kind==='gl')return Response.json({error:'Unrecognized transaction date at row 25.'},{status:422});
   return Response.json({kind:b.kind,data:{ok:true},source_hash:b.kind});
  }
  throw Error('Must not assess after invalid GL');
 }}};
 try{
  const r=await worker.fetch(req('/api/process',{method:'POST',cookie:'sa_access=synthetic',body:{run_id:'r',version:2}}),e);
  assert.equal(r.status,422);assert.match((await r.json()).error,/General Ledger failed validation/);
  assert.equal(seen[1].action,'fail');assert(!seen.some(x=>x.action==='complete'));
 }finally{globalThis.fetch=original}
});
test('mismatched month stays blocked with meaningful error',async()=>{
 const original=globalThis.fetch;const seen=[];
 globalThis.fetch=async(url,options)=>{
  const b=JSON.parse(options.body);seen.push(b);
  if(b.action==='prepare')return Response.json({version:3,payload:{month:'2026-09',files:{pnl:'a',bs:'b',gl:'c',drs:'d'}}});
  return Response.json({saved:true});
 };
 const e={...env,ENGINE:{fetch:async()=>Response.json({month:'2026-08',source_map:{pnl:'pnl',bs:'bs',gl:'gl',drs:'drs'}})}};
 try{
  const r=await worker.fetch(req('/api/process',{method:'POST',cookie:'sa_access=synthetic',body:{run_id:'run',version:2}}),e);
  assert.equal(r.status,422);assert.match((await r.json()).error,/2026-08/);
  assert.equal(seen[1].action,'fail');assert(!seen.some(x=>x.action==='complete'));
 }finally{globalThis.fetch=original}
});
test('preflight inspection uses authenticated member and privately bound Python',async()=>{
 const original=globalThis.fetch;const seen=[];
 globalThis.fetch=async(url,options)=>{
  const b=JSON.parse(options.body);seen.push(b);
  if(b.action==='session')return Response.json({email:'user@gatpsolutions.com',role:'staff'});
  throw Error('Unexpected mock action');
 };
 const e={...env,ENGINE:{fetch:async r=>{assert.equal(new URL(r.url).pathname,'/inspect');return Response.json({month:'2026-08',source_map:{pnl:'drs',bs:'gl',gl:'bs',drs:'pnl'}})}}};
 try{
  const r=await worker.fetch(req('/api/inspect',{method:'POST',cookie:'sa_access=synthetic',body:{files:{pnl:'a',bs:'b',gl:'c',drs:'d'}}}),e);
  assert.equal(r.status,200);assert.equal((await r.json()).month,'2026-08');assert.equal(seen[0].action,'session');
 }finally{globalThis.fetch=original}
});
test('Python inspection error is saved and reported without approving the run',async()=>{
 const original=globalThis.fetch;const seen=[];
 globalThis.fetch=async(url,options)=>{
  const b=JSON.parse(options.body);seen.push(b);
  return Response.json(b.action==='prepare'?{version:3,payload:{files:{pnl:'a',bs:'b',gl:'c',drs:'d'}}}:{saved:true});
 };
 const e={...env,ENGINE:{fetch:async()=>Response.json({error:'Synthetic blocking failure'},{status:422})}};
 try{
  const r=await worker.fetch(req('/api/process',{method:'POST',cookie:'sa_access=synthetic',body:{run_id:'test-run',version:2}}),e);
  assert.equal(r.status,422);assert.equal(seen[1].action,'fail');
  assert.equal(seen[1].error,'Synthetic blocking failure');
  assert(!seen.some(x=>x.action==='complete'));
 }finally{globalThis.fetch=original}
});


test('health refuses a deployed Python engine without staged parse and assess',async()=>{
 const orig=globalThis.fetch;globalThis.fetch=async()=>Response.json({database:true,storage_private:true});
 try{
  const oldEngine={...env,ENGINE:{fetch:async()=>Response.json({version:'old',client_ready:false})}};
  const r=await worker.fetch(req('/api/health'),oldEngine);
  assert.equal(r.status,503);assert.equal((await r.json()).python_compatible,false);
 }finally{globalThis.fetch=orig}
});
