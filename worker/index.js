import HTML from '../frontend/index.html';
import SCRIPT from '../frontend/app.js';
import CSS from '../frontend/style.css';
const SB='https://bvefxipftyvtsurocqqs.supabase.co';
const KEY='sb_publishable_clmwePv7xg264bthpt-BMA_NTB8KMOy';
const security={'X-Robots-Tag':'noindex, nofollow, noarchive','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','Permissions-Policy':'camera=(), microphone=(), geolocation=()','Strict-Transport-Security':'max-age=31536000; includeSubDomains','Cache-Control':'no-store'};
const csp="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' https://bvefxipftyvtsurocqqs.supabase.co; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'";
function json(data,status=200,extra={}){return new Response(JSON.stringify(data),{status,headers:{...security,'Content-Type':'application/json',...extra}});}
function cookies(req){return Object.fromEntries((req.headers.get('Cookie')||'').split(';').map(x=>x.trim().split('=')).filter(x=>x.length===2));}
function setCookies(response,session){const h=new Headers(response.headers);const age=session?Math.min(Number(session.expires_in)||3600,86400):0;h.append('Set-Cookie',`sa_access=${session?.access_token||''}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${age}`);h.append('Set-Cookie',`sa_refresh=${session?.refresh_token||''}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${session?604800:0}`);return new Response(response.body,{status:response.status,headers:h});}
async function readBody(req,limit=100000){if(Number(req.headers.get('Content-Length')||0)>limit)throw Error('Request too large.');const text=await req.text();if(text.length>limit)throw Error('Request too large.');try{return JSON.parse(text||'{}')}catch{throw Error('Invalid request.')}}
async function sbAuth(path,body,token){const r=await fetch(SB+'/auth/v1/'+path,{method:'POST',headers:{apikey:KEY,'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},body:JSON.stringify(body)});let data;try{data=await r.json()}catch{data={}}return {ok:r.ok,status:r.status,data};}
async function edge(env,token,body){const r=await fetch(SB+'/functions/v1/saint-workspace',{method:'POST',headers:{'Content-Type':'application/json','X-Saint-Gateway':env.GATEWAY_SECRET,...(token?{Authorization:'Bearer '+token}:{})},body:JSON.stringify(body)});let d;try{d=await r.json()}catch{d={error:'Workspace service returned an invalid response.'}}return {ok:r.ok,status:r.status,data:d};}
async function engine(env,path,body){const r=await env.ENGINE.fetch(new Request('https://engine/'+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})}));let d;try{d=await r.json()}catch{d={error:'Python service unavailable.'}}return {ok:r.ok,status:r.status,data:d};}
const direct=['session','runs','run','settings','create','review','download','delete','members','save_member','baseline'];
async function routed(req,env,url){
 const path=url.pathname;const ck=cookies(req);let token=ck.sa_access,session;
 if(path==='/api/health'){
  const p=await engine(env,'health');const s=await edge(env,null,{action:'health'});
  return json({app:'Saint Eyewear reporting',python:p.ok,database:s.ok,client_ready:false,mode:'internal_review',release_blockers:['Original templates missing','August/September issued-pack acceptance not completed'],version:p.data.version||null},p.ok&&s.ok?200:503);
 }
 if(path==='/api/auth/signout'){
  if(token)await sbAuth('logout?scope=local',{},token);
  return setCookies(json({signed_out:true}),null);
 }
 if(path==='/api/auth/signin'||path==='/api/auth/signup'){
  const b=await readBody(req,3000);const email=String(b.email||'').trim().toLowerCase();
  if(!/^[^@\s]+@gatpsolutions\.com$/.test(email)||typeof b.password!=='string'||b.password.length<8)return json({error:'Use an approved GATP email and a password of at least 8 characters.'},400);
  const signup=path.endsWith('signup');
  const r=await sbAuth(signup?'signup':'token?grant_type=password',{email,password:b.password});
  if(!r.ok)return json({error:r.data.msg||r.data.message||r.data.error_description||'Sign-in failed.'},r.status);
  if(!r.data.access_token)return json({confirmation_required:true,message:'Check your email to confirm the account, then return here to sign in. Creating an account does not grant workspace access.'});
  const check=await edge(env,r.data.access_token,{action:'session'});if(!check.ok){await sbAuth('logout?scope=local',{},r.data.access_token);return json(check.data,check.status)}
  return setCookies(json(check.data),r.data);
 }
 if(!token&&ck.sa_refresh){const rr=await sbAuth('token?grant_type=refresh_token',{refresh_token:ck.sa_refresh});if(rr.ok){session=rr.data;token=session.access_token}}
 if(!token)return setCookies(json({error:'Sign in required.'},401),null);
 const action=path.replace('/api/','');const b=req.method==='POST'?await readBody(req):{};
 let out;
 if(direct.includes(action)){
  out=await edge(env,token,{...b,action});
  if(action==='settings'&&out.ok){const conf=await engine(env,'config');if(conf.ok)out.data.defaults=conf.data;else out={ok:false,status:503,data:{error:'Python configuration unavailable.'}}}
 }else if(action==='save_settings'){
  const cfg=b.config;
  if(!cfg||typeof cfg!=='object'||!cfg.groups||!cfg.thresholds)return json({error:'Account groups and thresholds are required.'},400);
  const seen=new Set();for(const [group,names] of Object.entries(cfg.groups)){if(!['revenue','cogs','marketing','operating','other_income'].includes(group)||!Array.isArray(names))return json({error:'Invalid account groups.'},400);for(const n of names){if(typeof n!=='string'||!n.trim()||seen.has(n.trim().toLowerCase()))return json({error:'Duplicate or invalid account mapping.'},400);seen.add(n.trim().toLowerCase());}}
  const defaults=await engine(env,'config');if(!defaults.ok)return json({error:'Configuration engine unavailable.'},503);
  for(const k of Object.keys(defaults.data.thresholds)){const n=Number(cfg.thresholds[k]);if(!Number.isFinite(n)||n<0)return json({error:'Every threshold must be a nonnegative number.'},400)}
  out=await edge(env,token,{action:'save_settings',config:{...defaults.data,...cfg,approved_templates:false,acceptance_passed:false},retention_confirmed:b.retention_confirmed});
 }else if(action==='process'){
  const prepared=await edge(env,token,{action:'prepare',run_id:b.run_id,version:b.version});
  if(!prepared.ok)out=prepared;
  else{
   const version=prepared.data.version;let processed;
   try{processed=await engine(env,'process',prepared.data.payload)}catch{processed={ok:false,status:503,data:{error:'Python processing failed. Reopen the run and retry.'}}}
   if(processed.ok)out=await edge(env,token,{action:'complete',run_id:b.run_id,version,result:processed.data});
   else{await edge(env,token,{action:'fail',run_id:b.run_id,version,error:processed.data.error});out=processed;}
  }
 }else if(action==='generate'){
  const p=await edge(env,token,{action:'generation',run_id:b.run_id,version:b.version,kind:b.kind});
  if(!p.ok)out=p;else{const d=await engine(env,'generate',{kind:b.kind,run:p.data.run});out=d.ok?await edge(env,token,{action:'store',run_id:b.run_id,version:b.version,kind:b.kind,document:d.data}):d;}
 }else return json({error:'Unknown operation.'},404);
 const response=json(out.data,out.status);return session?setCookies(response,session):response;
}
export default {
 async fetch(req,env){
  const url=new URL(req.url);
  try{
   if(url.pathname.startsWith('/api/')){
    if(!env.GATEWAY_SECRET||!env.ENGINE)return json({error:'Secure application services are not configured.'},503);
    if(!['GET','POST'].includes(req.method))return json({error:'Method not allowed.'},405);
    if(req.method==='POST'&&req.headers.get('Origin')!==url.origin)return json({error:'Cross-origin request rejected.'},403);
    if(req.method!=='POST'&&!['/api/session','/api/health','/api/runs','/api/settings','/api/members'].includes(url.pathname))return json({error:'Method not allowed.'},405);
    return await routed(req,env,url);
   }
   if(req.method!=='GET'&&req.method!=='HEAD')return json({error:'Method not allowed.'},405);
   if(url.pathname==='/robots.txt')return new Response('User-agent: *\nDisallow: /\n',{headers:{...security,'Content-Type':'text/plain'}});
   const vendors={'/vendor/react.js':'https://unpkg.com/react@18.3.1/umd/react.production.min.js','/vendor/react-dom.js':'https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js'};
   if(vendors[url.pathname]){const upstream=await fetch(vendors[url.pathname],{cf:{cacheTtl:86400,cacheEverything:true}});if(!upstream.ok)return json({error:'Pinned interface dependency unavailable.'},503);return new Response(upstream.body,{headers:{...security,'Content-Type':'application/javascript','Cache-Control':'public, max-age=86400'}});}
   const staticFiles={'/':[HTML,'text/html; charset=utf-8'],'/app.js':[SCRIPT,'application/javascript; charset=utf-8'],'/style.css':[CSS,'text/css; charset=utf-8']};
   const item=staticFiles[url.pathname];if(!item)return json({error:'Not found'},404);
   return new Response(req.method==='HEAD'?null:item[0],{headers:{...security,'Content-Type':item[1],'Content-Security-Policy':csp}});
  }catch{return json({error:'The operation could not be completed. Your report has not been approved.'},500);}
 },
 async scheduled(event,env,ctx){ctx.waitUntil(edge(env,null,{action:'cleanup'}).then(r=>{if(!r.ok)throw Error('RETENTION_FAILED')}));}
};
