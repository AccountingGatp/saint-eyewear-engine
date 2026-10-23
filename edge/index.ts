import { createClient } from 'npm:@supabase/supabase-js@2.78.0';
const SECRET_HASH=Deno.env.get('SAINT_GATEWAY_SHA256')||'';
const URL=Deno.env.get('SUPABASE_URL')!;
const db=createClient(URL,Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,{auth:{persistSession:false,autoRefreshToken:false}});
const BUCKET='saint-private';
const kinds=['financial','deepview','quick','exceptions'];
const sourceKeys=['pnl','bs','gl','drs'];
class Failure extends Error { constructor(public status:number,message:string){super(message);} }
function bad(message:string,status=400):never{throw new Failure(status,message);}
function checked<T>(res:{data:T,error:any}):T {if(res.error)throw new Failure(500,'Database or storage operation failed. No report was approved.');return res.data;}
function response(body:unknown,status=200){return new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});}
async function digest(value:string){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)))).map(v=>v.toString(16).padStart(2,'0')).join('');}
function month(value:any){if(typeof value!=='string'||!/^20\d\d-(0[1-9]|1[0-2])$/.test(value))bad('A reporting month is required.');return value;}
function previousMonth(m:string){const [y,n]=m.split('-').map(Number);return new Date(Date.UTC(y,n-2,1)).toISOString().slice(0,7);}
function uid(v:any){if(typeof v!=='string'||!/^[0-9a-f-]{36}$/i.test(v))bad('Invalid run ID.');return v;}
function to64(buffer:ArrayBuffer){const a=new Uint8Array(buffer);let s='';for(let i=0;i<a.length;i+=16384)s+=String.fromCharCode(...a.subarray(i,i+16384));return btoa(s);}
function from64(s:string){return Uint8Array.from(atob(s),c=>c.charCodeAt(0));}
async function audit(run:string|null,user:string|null,event:string){checked(await db.from('saint_audit').insert({run_id:run,actor_id:user,event}));}
async function removeRun(run:any){
 const artifacts=checked(await db.from('saint_artifacts').select('path').eq('run_id',run.id))||[];
 const paths=[...Object.values(run.source_paths||{}),...artifacts.map((a:any)=>a.path)] as string[];
 for(let i=0;i<paths.length;i+=100)checked(await db.storage.from(BUCKET).remove(paths.slice(i,i+100)));
 checked(await db.from('runs').delete().eq('id',run.id));
}
Deno.serve(async req=>{
 try{
  if(req.method!=='POST')return response({error:'Method not allowed'},405);
  const secret=req.headers.get('X-Saint-Gateway')||'';
  if(!SECRET_HASH||!secret||await digest(secret)!==SECRET_HASH)return response({error:'Forbidden'},403);
  if(Number(req.headers.get('content-length')||0)>32_000_000)bad('Request too large.',413);
  const text=await req.text();if(text.length>32_000_000)bad('Request too large.',413);
  let b:any;try{b=JSON.parse(text)}catch{bad('Invalid request JSON.')}
  const action=String(b.action||'');
  if(action==='health'){
   const s=checked(await db.from('saint_settings').select('id,retention_confirmed').eq('id',1).single());
   const bucket=checked(await db.storage.getBucket(BUCKET));return response({database:true,storage_private:bucket.public===false,client_ready:false,retention_confirmed:s.retention_confirmed});
  }
  if(action==='cleanup'){
   const settings=checked(await db.from('saint_settings').select('*').eq('id',1).single());
   if(!settings.retention_confirmed)return response({skipped:'Retention periods await owner confirmation.'});
   const sourceBefore=new Date(Date.now()-30*86400000).toISOString();
   const keepBefore=new Date();keepBefore.setUTCMonth(keepBefore.getUTCMonth()-24);
   const expired=checked(await db.from('runs').select('*').lt('created_at',keepBefore.toISOString()).limit(100))||[];
   for(const r of expired){await removeRun(r);await audit(r.id,null,'retention_run_deleted');}
   const sources=checked(await db.from('runs').select('*').lt('created_at',sourceBefore).eq('source_expired',false).limit(100))||[];
   for(const r of sources){const paths=Object.values(r.source_paths||{}) as string[];if(paths.length)checked(await db.storage.from(BUCKET).remove(paths));checked(await db.from('runs').update({source_expired:true,updated_at:new Date().toISOString()}).eq('id',r.id));await audit(r.id,null,'retention_sources_deleted');}
   return response({deleted_runs:expired.length,expired_sources:sources.length});
  }
  const token=(req.headers.get('Authorization')||'').replace(/^Bearer /,'');
  if(!token)return response({error:'Sign in required.'},401);
  const auth=await db.auth.getUser(token);if(auth.error||!auth.data.user)return response({error:'Session expired. Sign in again.'},401);
  const user=auth.data.user;const email=(user.email||'').toLowerCase();
  if(!user.email_confirmed_at)bad('Confirm your email before accessing financial information.',403);
  const member=checked(await db.from('saint_members').select('role,active').eq('email',email).maybeSingle());
  if(!member?.active)bad('This account is not approved for the Saint Eyewear workspace.',403);
  const leader=member.role==='team_leader',reviewer=leader||member.role==='reviewer';
  function requireLeader(){if(!leader)bad('Only the team leader can perform this operation.',403);}
  async function loadRun(id:string){const r=checked(await db.from('runs').select('*').eq('id',uid(id)).maybeSingle());if(!r||(!reviewer&&r.owner_id!==user.id))bad('Run not found.',404);return r;}
  async function update(r:any,values:any,version:number){if(version!==r.version)bad('This run changed. Reopen it before saving.',409);const x=checked(await db.from('runs').update({...values,updated_at:new Date().toISOString()}).eq('id',r.id).eq('version',version).select().maybeSingle());if(!x)bad('Another operation changed this run. Reopen it.',409);return x;}
  function requireReview(r:any,requireRole=true){if(requireRole&&!reviewer)bad('Reviewer access required.',403);if(!['review','ready','generated'].includes(r.status)||r.flags.some((f:any)=>f.severity==='Block'))bad('Resolve blocking issues first.',409);if(r.flags.some((f:any)=>f.severity==='Review'&&!String(r.notes?.[f.id]||'').trim()))bad('Every Review flag needs an explanation.',409);if(!r.reviewed_user_id||!r.reviewed_at||!r.reviewed_by)bad('Reviewer sign-off required.',409);}
  if(action==='session')return response({email,role:member.role,client_ready:false});
  if(action==='runs'){
   let query=db.from('runs').select('id,report_month,status,created_at,updated_at,version,reviewed_by,source_expired,error_message').order('created_at',{ascending:false}).limit(100);
   if(!reviewer)query=query.eq('owner_id',user.id);
   return response({runs:checked(await query)});
  }
  if(action==='run')return response({run:await loadRun(b.run_id)});
  if(action==='settings'){
   const settings=checked(await db.from('saint_settings').select('*').eq('id',1).single());return response({settings});
  }
  if(action==='save_settings'){
   requireLeader();if(!b.config||typeof b.config!=='object')bad('Invalid configuration.');
   const conf={...b.config,client:'Saint Eyewear Pty Ltd',currency:'AUD',financial_year_start:7,approved_templates:false,acceptance_passed:false};
   checked(await db.from('saint_settings').update({config:conf,retention_confirmed:b.retention_confirmed===true,updated_at:new Date().toISOString()}).eq('id',1));await audit(null,user.id,'configuration_updated');return response({saved:true});
  }
  if(action==='members'){
   requireLeader();return response({members:checked(await db.from('saint_members').select('email,role,active').order('email'))});
  }
  if(action==='save_member'){
   requireLeader();const e=String(b.email||'').trim().toLowerCase();if(!/^[^@\s]+@gatpsolutions\.com$/.test(e)||!['staff','reviewer','team_leader'].includes(b.role))bad('Enter a GATP email and valid role.');
   if(e===email&&(b.active===false||b.role!=='team_leader'))bad('You cannot remove your own team-leader access.');
   checked(await db.from('saint_members').upsert({email:e,role:b.role,active:b.active!==false}));await audit(null,user.id,'membership_updated');return response({saved:true});
  }
  if(action==='baseline'){
   requireLeader();const m=month(b.month);if(!b.verified||String(b.source||'').trim().length<10)bad('Identify the original issued pack and confirm these are its exact figures.');
   const values=b.figures;if(!values||Array.isArray(values)||typeof values!=='object'||!Object.keys(values).length||Object.keys(values).length>1000)bad('Provide account-to-amount JSON.');
   for(const [k,v] of Object.entries(values))if(k.length>200||typeof v!=='string'||!/^[-+]?\d+(\.\d+)?$/.test(v))bad('Baseline amounts must be numeric strings, not guesses.');
   checked(await db.from('saint_issued').insert({report_month:m+'-01',figures:values,source_description:String(b.source).slice(0,1000),created_by:user.id}));await audit(null,user.id,'issued_baseline_added');return response({saved:true});
  }
  if(action==='create'){
   const m=month(b.month);const sizes=b.sizes;if(!sizes||sourceKeys.some(k=>!Number.isInteger(sizes[k])||sizes[k]<1||sizes[k]>5_000_000)||Object.values(sizes).reduce((a:any,v:any)=>a+v,0)>12_000_000)bad('Each file must be under 5 MB; the four files together must be under 12 MB.');
   const settings=checked(await db.from('saint_settings').select('config').eq('id',1).single());
   const id=crypto.randomUUID();const paths=Object.fromEntries(sourceKeys.map(k=>[k,`${user.id}/${id}/source/${k}.xlsx`]));
   checked(await db.from('runs').insert({id,owner_id:user.id,report_month:m+'-01',source_paths:paths,config_snapshot:settings.config}));
   const uploads:any={};for(const k of sourceKeys)uploads[k]=checked(await db.storage.from(BUCKET).createSignedUploadUrl(paths[k],{upsert:false}));
   await audit(id,user.id,'run_created');return response({run_id:id,version:1,uploads});
  }
  const r=await loadRun(b.run_id);
  if(action==='prepare'){
   if(r.source_expired)bad('Source files expired under retention rules. Create a new run to process new exports.',409);
   if(r.processing_until&&Date.parse(r.processing_until)>Date.now())bad('This run is already processing.',409);
   const now=new Date(),lease=new Date(now.getTime()+180000).toISOString();
   const currentSettings=checked(await db.from('saint_settings').select('config').eq('id',1).single());
   const locked=await update(r,{config_snapshot:currentSettings.config,processing_until:lease,version:r.version+1,status:'uploaded',result_paths:{},figures:{},flags:[],notes:{},reviewed_by:null,reviewed_at:null,reviewed_user_id:null,error_message:null},b.version);
   try {
   const files:any={};let total=0;
   for(const k of sourceKeys){const path=r.source_paths[k];if(!path||!path.startsWith(`${r.owner_id}/${r.id}/source/`))bad('Invalid source-file path.');const blob=checked(await db.storage.from(BUCKET).download(path));total+=blob.size;if(blob.size>5_000_000||total>12_000_000)bad('Uploaded workbook size exceeds this deployment limit.');files[k]=to64(await blob.arrayBuffer());}
   const m=r.report_month.slice(0,7),pm=previousMonth(m);
   const prevs=checked(await db.from('runs').select('figures').eq('report_month',pm+'-01').in('status',['review','ready','generated']).order('updated_at',{ascending:false}).limit(1))||[];
   const p=prevs[0]?.figures;const previous=p?{vendors:p.vendors,drs_totals:p.drs?.totals,accounts:p.pnl?.accounts}:{};
   const rows=checked(await db.from('saint_issued').select('report_month,figures').lte('report_month',r.report_month).gte('report_month',previousMonth(pm)+'-01').order('created_at',{ascending:false}))||[];
   const issued:any={};for(const row of rows){const k=row.report_month.slice(0,7);if(!issued[k])issued[k]=row.figures;}
   return response({version:locked.version,payload:{month:m,files,config:currentSettings.config,previous,issued}});
   } catch(error) {
    await db.from('runs').update({status:'error',processing_until:null,error_message:'Source preparation failed. Check all four uploaded files.'}).eq('id',r.id).eq('version',locked.version);
    throw error;
   }
  }
  if(action==='complete'){
   if(!r.processing_until||!b.result||b.result.month!==r.report_month.slice(0,7))bad('No valid processing operation is active.',409);
   const f={...b.result,client_ready:false};await update(r,{figures:f,flags:f.flags,status:f.status,processing_until:null,error_message:null},b.version);await audit(r.id,user.id,'processing_completed');return response({saved:true});
  }
  if(action==='fail'){
   if(r.version===b.version)await update(r,{status:'error',error_message:String(b.error||'Processing failed').slice(0,1000),processing_until:null},b.version);
   return response({saved:true});
  }
  if(action==='review'){
   if(!reviewer)bad('Reviewer access required.',403);
   if(!['review','ready','generated'].includes(r.status))bad('Process the run and resolve blocks first.',409);
   const notes:any={};for(const f of r.flags){const s=String(b.notes?.[f.id]||'').trim();if(s.length>5000)bad('A reviewer note is too long.');if(s)notes[f.id]=s;}
   if(b.signoff&&(r.flags.some((f:any)=>f.severity==='Block')||r.flags.some((f:any)=>f.severity==='Review'&&!notes[f.id])))bad('Clear all blocks and explain every Review flag before signing off.',409);
   const out=await update(r,{notes,reviewed_by:b.signoff?email:null,reviewed_at:b.signoff?new Date().toISOString():null,reviewed_user_id:b.signoff?user.id:null,version:r.version+1,result_paths:{},status:'review'},b.version);await audit(r.id,user.id,b.signoff?'review_signed':'review_saved');return response({run:out});
  }
  if(action==='generation'){
   requireReview(r);if(b.version!==r.version)bad('Run changed. Reopen it.',409);if(!kinds.includes(b.kind))bad('Invalid document type.');return response({run:r});
  }
  if(action==='store'){
   requireReview(r);if(b.version!==r.version||!kinds.includes(b.kind)||!b.document?.draft)bad('Generation version or draft status is invalid.',409);
   const d=b.document;if(typeof d.content!=='string'||d.content.length>12_000_000)bad('Generated document too large.');
   const id=crypto.randomUUID(),path=`${r.owner_id}/${r.id}/output/${id}.docx`;
   checked(await db.storage.from(BUCKET).upload(path,from64(d.content),{contentType:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',upsert:false}));
   checked(await db.from('saint_artifacts').insert({run_id:r.id,kind:b.kind,path,filename:String(d.filename).slice(0,250)}));
   const stored=await update(r,{result_paths:{...r.result_paths,[b.kind]:path},status:'generated',version:r.version+1},b.version);await audit(r.id,user.id,'draft_generated_'+b.kind);return response({saved:true,version:stored.version});
  }
  if(action==='download'){
   if(!kinds.includes(b.kind))bad('Invalid document type.');const path=r.result_paths?.[b.kind];if(!path)bad('Generate a reviewed draft first.',404);requireReview(r,false);
   const a=checked(await db.from('saint_artifacts').select('filename').eq('path',path).single());const signed=checked(await db.storage.from(BUCKET).createSignedUrl(path,60,{download:a.filename}));return response({url:signed.signedUrl});
  }
  if(action==='delete'){
   requireLeader();if(b.confirm!==r.id)bad('Deletion must be explicitly confirmed.');await removeRun(r);await audit(r.id,user.id,'run_deleted');return response({deleted:true});
  }
  return response({error:'Unknown operation.'},404);
 }catch(e){if(e instanceof Failure)return response({error:e.message},e.status);return response({error:'The operation failed. No client pack was approved.'},500);}
});
