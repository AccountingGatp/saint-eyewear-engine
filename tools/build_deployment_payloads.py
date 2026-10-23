"""Build reviewable deployment payloads. No network calls and no embedded secrets."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build'; OUT.mkdir(exist_ok=True)
def part(name,mime,text): return {'name':name,'content_type':mime,'content':text}
# The package namespace is preserved to avoid relative-import ambiguity.
py=[part('entry.py','text/x-python','from backend.entry import Default\n')]
for path in sorted((ROOT/'backend').glob('*.py')):
 py.append(part(path.relative_to(ROOT).as_posix(),'text/x-python',path.read_text()))
engine={'script_name':'saint-eyewear-engine','metadata':{'main_module':'entry.py','compatibility_date':'2026-10-23','compatibility_flags':['python_workers','disable_python_external_sdk']},'parts':py,'public_route':False}
worker=(ROOT/'worker/index.js').read_text().replace('../frontend/index.html','./index.html').replace('../frontend/app.js','./app.js').replace('../frontend/style.css','./style.css')
web={'script_name':'saint-eyewear','metadata':{'main_module':'worker.js','compatibility_date':'2026-10-23','observability':{'enabled':False},'bindings':[{'type':'service','name':'ENGINE','service':'saint-eyewear-engine'}]},'parts':[part('worker.js','application/javascript',worker)]+[part(n,'text/plain',(ROOT/'frontend'/n).read_text()) for n in ('index.html','app.js','style.css')],'required_secret_binding':'GATEWAY_SECRET','public_route':True}
edge={'name':'saint-workspace','entrypoint_path':'index.ts','verify_jwt':False,'files':[{'name':'index.ts','content':(ROOT/'edge/index.ts').read_text()}],'required_environment_variable':'SAINT_GATEWAY_SHA256'}
for name,obj in [('python-worker',engine),('web-worker',web),('supabase-edge',edge)]:
 (OUT/(name+'.json')).write_text(json.dumps(obj,indent=2))
print('Created three plain-text deployment payloads in build/. No deployment performed.')
