"""Private Python Worker, callable only through a Cloudflare service binding."""
from workers import WorkerEntrypoint, Response
import json
from backend.core import process, inspect_uploads, parse_file, assess_parsed, DEFAULT_CONFIG, ValidationError, VERSION
from backend.documents import document

class Default(WorkerEntrypoint):
 async def fetch(self, request):
  try:
   path=str(request.url).split('?',1)[0].rsplit('/',1)[-1]
   if path=='health':return Response.json({'runtime':'Python','version':VERSION,'capabilities':['inspect','parse','assess','generate'],'client_ready':False})
   if path=='config':return Response.json(DEFAULT_CONFIG)
   if request.method!='POST':return Response.json({'error':'Method not allowed'},status=405)
   body=json.loads(await request.text())
   if path=='inspect':return Response.json(inspect_uploads(body))
   if path=='parse':return Response.json(parse_file(body))
   if path=='assess':return Response.json(assess_parsed(body))
   if path=='process':return Response.json(process(body))
   if path=='generate':return Response.json(document(body))
   return Response.json({'error':'Not found'},status=404)
  except ValidationError as e:return Response.json({'error':str(e)},status=422)
  except Exception as e:
   # Keep financial content and tracebacks out of the client response.
   print('Private Python engine failure: '+type(e).__name__)
   return Response.json({'error':'Internal Python engine error ('+type(e).__name__+'). No report was approved.'},status=500)
