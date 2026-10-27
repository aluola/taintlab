"""FastAPI transport for the local simulated Agent; no cloud or host tools."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlparse
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI,Request,Response,UploadFile,File
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse,StreamingResponse,PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal

from taintlab.model.client import load_config
from . import VERSION
from .catalog import catalog
from .projection import project_record
from .service import Service,ServiceError
from .uploads import parse_upload,UploadError

ROOT=Path(__file__).resolve().parents[3]
COOKIE='taintlab_browser'
MODES=('none','input_filter','taint_policy','policy_only')

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class NewSession(Strict):title:str=Field(default='新对话',max_length=60)
class RunInput(Strict):
    request_id:str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    task:str=Field(min_length=1,max_length=1800)
    mode:Literal['none','input_filter','taint_policy','policy_only']='taint_policy'
    seed:int=Field(default=11,ge=0,le=2147483647)
    document_ids:list[str]=Field(default_factory=lambda:['meeting'],max_length=3)
    recipient_id:str|None=Field(default=None,max_length=40)
    export_path:str|None=Field(default=None,max_length=80)
    private_mode:bool=False
    preview_id:str|None=Field(default=None,max_length=64)
class Confirmation(Strict):
    request_id:str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    action_hash:str=Field(pattern=r'^[a-f0-9]{64}$')
    approve:bool
class Preview(Strict):
    view:Literal['direct','indirect','encoding','segmented']
    technique:str=Field(max_length=40)
    encoding:str=Field(default='none',max_length=20)
    entry:str=Field(max_length=30)
    goal:str=Field(max_length=40)
    workflow:str=Field(default='query',max_length=30)
    seed:int=Field(default=11,ge=0,le=2147483647)

class Boundary:
    """Host/Origin/Fetch-Site gate and bounded request body before multipart parsing."""
    def __init__(self,app,port=8501,testing=False):
        self.app=app;self.hosts={f'127.0.0.1:{port}',f'localhost:{port}'}
        if testing:self.hosts.add('testserver')
        self.origins={'http://'+h for h in self.hosts}
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        headers={k.decode().lower():v.decode() for k,v in scope.get('headers',[])}
        invalid=headers.get('host') not in self.hosts or headers.get('origin') not in (None,*self.origins) or headers.get('sec-fetch-site')=='cross-site'
        if scope['method'] in ('POST','PUT','DELETE','PATCH') and headers.get('origin') not in self.origins:invalid=True
        if invalid:return await JSONResponse({'error':{'code':'origin_denied','message':'仅允许本机同源页面访问。'}},403)(scope,receive,send)
        if scope['method'] in ('POST','PUT','PATCH'):
            size=0;body=[]
            while True:
                message=await receive()
                if message['type']=='http.disconnect':return
                chunk=message.get('body',b'');size+=len(chunk)
                if size>3*1024*1024:return await JSONResponse({'error':{'code':'request_too_large','message':'请求体超过3MiB限制。'}},413)(scope,receive,send)
                body.append(chunk)
                if not message.get('more_body'):break
            delivered=False
            async def limited_receive():
                nonlocal delivered
                if not delivered:delivered=True;return {'type':'http.request','body':b''.join(body),'more_body':False}
                return await receive()
            receiver=limited_receive
        else:receiver=receive
        async def safe_send(message):
            if message['type']=='http.response.start':
                message['headers']=list(message.get('headers',[]))+[
                    (b'x-content-type-options',b'nosniff'),(b'referrer-policy',b'no-referrer'),
                    (b'content-security-policy',b"default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
                    (b'cache-control',b'no-store')]
            await send(message)
        return await self.app(scope,receiver,safe_send)

def create_app(root=ROOT,port=8501,backend_factory=None,testing=False,session_root=None):
    # Trusted process configuration only; no request can choose this path.
    # Acceptance can serve the real build while isolating its session ledger.
    root=Path(root).resolve();service=Service(session_root or root,backend_factory)
    @asynccontextmanager
    async def lifespan(app):
        yield
        await asyncio.to_thread(service.close)
    app=FastAPI(title='本地Agent对话靶场',version=VERSION,docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.service=service
    app.add_middleware(Boundary,port=port,testing=testing)
    def owner(request,mutate=False):
        user=service.authenticate(request.cookies.get(COOKIE))
        if mutate and not secrets.compare_digest(request.headers.get('X-TaintLab-CSRF',''),user['csrf']):raise ServiceError('csrf_denied','会话校验失效，请刷新页面。',403)
        return user['id']
    @app.exception_handler(ServiceError)
    async def service_error(request,exc):return JSONResponse({'error':{'code':exc.code,'message':exc.message}},exc.status)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):return JSONResponse({'error':{'code':'invalid_request','message':'参数不符合接口约定；不接受客户端授权、标签或执行记录。'}},422)
    @app.get('/api/health')
    def health():return {'status':'ok','service':'taintlab-web','version':VERSION}
    @app.get('/api/bootstrap')
    def bootstrap(request:Request,response:Response):
        user,new=service.owner(request.cookies.get(COOKIE))
        response.set_cookie(COOKIE,user['id'],httponly=True,samesite='strict',secure=False,max_age=7*86400,path='/')
        config=load_config();available=False
        if backend_factory:available=True
        else:
            endpoint=urlparse(config['endpoint']);url=f'http://{endpoint.netloc}/health'
            try:
                with httpx.Client(trust_env=False,follow_redirects=False,timeout=.8) as client:available=client.get(url).json().get('status')=='ok'
            except (httpx.HTTPError,ValueError):pass
        return {'version':VERSION,'csrf_token':user['csrf'],'model':{'available':available,'name':config['model'],'endpoint':config['endpoint'],'config':config},
                'catalog':catalog(),'sessions':service.sessions(user['id']),'modes':list(MODES)}
    @app.post('/api/sessions')
    def new_session(body:NewSession,request:Request):return service.create_session(owner(request,True),body.title)
    @app.get('/api/sessions')
    def sessions(request:Request):return {'sessions':service.sessions(owner(request))}
    @app.get('/api/sessions/{sid}')
    def get_session(sid:str,request:Request):return service.session(owner(request),sid)
    @app.post('/api/sessions/{sid}/runs',status_code=202)
    def new_run(sid:str,body:RunInput,request:Request):return service.start(owner(request,True),sid,body.model_dump())
    @app.get('/api/sessions/{sid}/runs/{rid}')
    def get_run(sid:str,rid:str,request:Request):return service.run(owner(request),sid,rid)
    @app.post('/api/sessions/{sid}/runs/{rid}/stop')
    def stop(sid:str,rid:str,body:Strict,request:Request):return service.stop(owner(request,True),sid,rid)
    @app.post('/api/sessions/{sid}/runs/{rid}/confirm',status_code=202)
    def confirm(sid:str,rid:str,body:Confirmation,request:Request):return service.confirm(owner(request,True),sid,rid,body.model_dump())
    @app.post('/api/sessions/{sid}/uploads')
    async def upload(sid:str,request:Request,file:UploadFile=File(...)):
        user=owner(request,True);service._session(user,sid)
        data=await file.read(2*1024*1024+1)
        await file.close()
        try:parsed=await asyncio.to_thread(parse_upload,file.filename or 'document.txt',data)
        except UploadError as exc:raise ServiceError(exc.code,exc.message) from None
        return service.upload(user,sid,file.filename or 'document.txt',parsed)
    @app.get('/api/sessions/{sid}/runs/{rid}/exports/{download_id}')
    def export(sid:str,rid:str,download_id:str,request:Request):
        text=service.export(owner(request),sid,rid,download_id)
        return PlainTextResponse(text,headers={'Content-Disposition':'attachment; filename="approved_export.txt"'})
    @app.get('/api/sessions/{sid}/events')
    async def events(sid:str,request:Request,after:int=0):
        user=owner(request);service._session(user,sid)
        try:cursor=max(0,after,int(request.headers.get('last-event-id','0')))
        except ValueError:raise ServiceError('invalid_cursor','事件游标无效。') from None
        async def stream():
            current=cursor;last_ping=0
            while not await request.is_disconnected():
                items=await asyncio.to_thread(service.events,user,sid,current)
                for event in items:
                    current=event['sequence']
                    yield 'id: '+str(current)+'\nevent: update\ndata: '+json.dumps(event,ensure_ascii=False,separators=(',',':'))+'\n\n'
                if time.monotonic()-last_ping>10:yield ': heartbeat\n\n';last_ping=time.monotonic()
                await asyncio.sleep(.25)
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no'})
    @app.get('/api/templates')
    def templates(request:Request):
        owner(request)
        from taintlab.attacks.interactive import list_presets
        return {'templates':list_presets()}
    @app.post('/api/sessions/{sid}/previews')
    def preview(sid:str,body:Preview,request:Request):
        user=owner(request,True);service._session(user,sid)
        from taintlab.attacks.interactive import build_preview
        try:result=build_preview(**body.model_dump())
        except ValueError:raise ServiceError('invalid_template','模板参数组合不受支持。') from None
        return service.add_preview(user,sid,result)
    campaigns={
        'historical_main':('results/main','v1 三种主配置','1.0.0',True),
        'historical_ablation':('results/ablation','v1 权限消融','1.0.0',True),
        'v2_baseline':('results/v2/baseline','v2 原72+36完整比较','2.0.0',False),
        'v2_external':('results/v2/external','v2 公开来源适配扩展','2.0.0',False),
    }
    @app.get('/api/results')
    def results(request:Request):
        owner(request);output=[]
        for identifier,(directory,label,version,historical) in campaigns.items():
            folder=root/directory;manifest_path=folder/'experiment_manifest.json'
            if not manifest_path.exists():continue
            manifest=json.loads(manifest_path.read_text(encoding='utf-8'));summary_path=folder/'summary.json'
            summary=json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else {}
            count=len(list((folder/'records').glob('*.json')));planned=manifest['planned_runs']
            output.append({'id':identifier,'label':label,'version':version,'historical':historical,'planned_runs':planned,'completed_runs':count,
                           'complete':count==planned and summary_path.exists(),'summary':summary,'manifest':manifest})
        return {'campaigns':output}
    @app.get('/api/replays')
    def replays(request:Request,campaign:str='historical_main',case_id:str='',mode:str='',limit:int=200):
        owner(request)
        if campaign not in campaigns:raise ServiceError('not_found','未知实验版本。',404)
        directory,label,version,_=campaigns[campaign];items=[]
        for p in sorted((root/directory/'records').glob('*.json')):
            r=json.loads(p.read_text(encoding='utf-8'))
            if case_id and case_id not in r.get('case_id',''):continue
            if mode and mode!=r.get('mode'):continue
            items.append({k:r.get(k) for k in ('case_id','mode','seed','status')}|{'record_id':p.stem,'version':version})
            if len(items)>=min(max(limit,1),2000):break
        return {'records':items}
    @app.get('/api/replays/{campaign}/{record_id}')
    def replay(campaign:str,record_id:str,request:Request):
        owner(request)
        if campaign not in campaigns or not re.fullmatch(r'[a-f0-9]{24,32}',record_id):raise ServiceError('not_found','运行不存在。',404)
        directory,label,version,_=campaigns[campaign];p=root/directory/'records'/(record_id+'.json')
        if not p.exists():raise ServiceError('not_found','运行不存在。',404)
        record=json.loads(p.read_text(encoding='utf-8'))
        tokens=re.findall(r'CANARY_[0-9a-f]{32}',json.dumps(record,ensure_ascii=False))
        return project_record(record,phase='真实运行记录回放',canaries=list(set(tokens)),historical=True,version=version)
    static=root/'frontend/dist'
    if static.is_dir():app.mount('/',StaticFiles(directory=static,html=True),name='frontend')
    return app
