"""Private Python Worker, callable only through a Cloudflare service binding."""
from workers import WorkerEntrypoint, Response
import json
from backend.core import process, DEFAULT_CONFIG, ValidationError, VERSION
from backend.documents import document

class Default(WorkerEntrypoint):
 async def fetch(self, request):
  try:
   path=str(request.url).split('?',1)[0].rsplit('/',1)[-1]
   if path=='health':return Response.json({'runtime':'Python','version':VERSION,'client_ready':False})
   if path=='config':return Response.json(DEFAULT_CONFIG)
   if request.method!='POST':return Response.json({'error':'Method not allowed'},status=405)
   body=json.loads(await request.text())
   if path=='process':return Response.json(process(body))
   if path=='generate':return Response.json(document(body))
   return Response.json({'error':'Not found'},status=404)
  except ValidationError as e:return Response.json({'error':str(e)},status=422)
  except Exception:return Response.json({'error':'Unsupported input or processing failure. No report was approved.'},status=500)
