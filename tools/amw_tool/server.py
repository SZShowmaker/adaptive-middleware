"""Local editor. No remote service, no application telemetry."""
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .model import load_project, validate, validate_types, loads, routes
from .generate import generate
from .cli import ROOT, save_bundle
from . import qos
from .paths import project_paths

def serve(project, config, port):
    initial=load_project(project)['bundle'];token=secrets.token_hex(24)
    state={'model':initial,'job':{'status':'idle'},'lock':threading.Lock(),'cancel':threading.Event()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def response(self,value,status=200):
            body=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if self.headers.get('Host','') not in (f'127.0.0.1:{port}',f'localhost:{port}'):self.response({'error':'invalid host'},403);return
            path=urlsplit(self.path).path
            if path=='/':
                data=(ROOT/'ui/index.html').read_text(encoding='utf-8').replace('__TOKEN__',token).encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            elif path in ('/types.js','/qos.js','/type-picker.js','/workspace.js','/paths.js'):
                data=(ROOT/'ui'/path[1:]).read_bytes();self.send_response(200);self.send_header('Content-Type','text/javascript; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            elif path=='/api/qos-catalog':self.response(qos.catalogue())
            elif path=='/api/model':self.response(state['model'])
            elif path=='/api/editor-config':self.response({'root':str(ROOT),'default_delivery_root':str(ROOT/'out/delivery')})
            elif path=='/api/job':self.response(state['job'])
            else:self.response({'error':'not found'},404)
        def do_POST(self):
            if self.headers.get('X-AMW-Token')!=token:self.response({'error':'invalid editor token'},403);return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16*1024*1024:raise ValueError('request size invalid')
                data=loads(self.rfile.read(length).decode());path=urlsplit(self.path).path
                if path=='/api/parse':self.response(loads(data['text']));return
                if path=='/api/paths':self.response(project_paths(ROOT,data['project_id'],data.get('delivery_root','')));return
                if path=='/api/types':
                    validate_types(data);self.response({'valid':True});return
                if path=='/api/qos':
                    from .model import fail
                    qos.validate_configuration(data,fail)
                    self.response({'valid':True,'note':'QoS 字段与一致性检查通过；生成前会检查整个工程的通信兼容性。'});return
                if path=='/api/save':
                    directory=project_paths(ROOT,data['project']['project_id'])['draft']
                    saved=save_bundle(directory,data);state['model']=data;self.response({'saved':str(saved),'note':'draft saved; validate before generation'});return
                if path=='/api/cancel':state['cancel'].set();self.response({'status':'cancel_requested'});return
                delivery_root=''
                if path=='/api/generate' and 'bundle' in data:
                    delivery_root=data.get('delivery_root','');data=data['bundle']
                model=validate(data)
                if path=='/api/validate':self.response({'valid':True,'warnings':model['warnings'],'qos':model['qos'],'routes':{i:routes(model,i) for i in model['instances']}});return
                if path=='/api/generate':
                    output=project_paths(ROOT,data['project']['project_id'],delivery_root)['output']
                    if not state['lock'].acquire(blocking=False):self.response({'error':'generation already running'},409);return
                    state['cancel'].clear();state['job']={'status':'running','output':output,'project_id':data['project']['project_id']}
                    def run():
                        try:manifest=generate(model,output,config,state['cancel']);state['job']={'status':'done','output':str(output),'manifest':{k:v for k,v in manifest.items() if k!='files'},'file_count':len(manifest['files'])}
                        except Exception as e:state['job']={'status':'failed','error':str(e)}
                        finally:state['lock'].release()
                    threading.Thread(target=run,daemon=True).start();self.response({'status':'running'});return
                self.response({'error':'not found'},404)
            except Exception as e:self.response({'error':str(e)},422)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print(f'AMW editor: http://127.0.0.1:{port} — Ctrl+C to stop',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
