"""Server-owned sessions, serialized controls and durable projected event streams."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime,timezone

from taintlab.agent.runtime import run_case,resume_run
from taintlab.evaluation.evaluator import evaluate
from taintlab.model.client import LocalModel
from .catalog import DOCUMENTS,metadata,create_runtime
from .projection import project_record

def now():return datetime.now(timezone.utc).isoformat()
def encoded(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))

class ServiceError(ValueError):
    def __init__(self,code,message,status=400):
        self.code=code;self.message=message;self.status=status;super().__init__(code)

class Service:
    def __init__(self,root,backend_factory=None):
        self.root=Path(root).resolve();self.directory=self.root/'results/v2/web_private'
        self.directory.mkdir(parents=True,exist_ok=True);self.database=self.directory/'sessions.sqlite'
        self.lock=threading.RLock();self.pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='agent')
        self.controls={};self.futures={};self.backend_factory=backend_factory or LocalModel
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS owners (id TEXT PRIMARY KEY, csrf TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL, created TEXT NOT NULL, documents TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, request_id TEXT NOT NULL, input_hash TEXT NOT NULL,
              data TEXT NOT NULL, UNIQUE(session_id,request_id));
            CREATE TABLE IF NOT EXISTS events (session_id TEXT NOT NULL, sequence INTEGER NOT NULL, run_id TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(session_id,sequence));
            CREATE TABLE IF NOT EXISTS previews (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS confirmation_requests (run_id TEXT NOT NULL, request_id TEXT NOT NULL, body_hash TEXT NOT NULL, PRIMARY KEY(run_id,request_id));
            ''')
            for row in db.execute('SELECT id,data FROM runs').fetchall():
                item=json.loads(row['data'])
                if item['record']['status'] in ('running','stopping'):
                    item['record']['status']='interrupted';item['phase']='interrupted'
                    item['warnings'].append('服务重启中断此运行；未自动重放工具动作。')
                    db.execute('UPDATE runs SET data=? WHERE id=?',(encoded(item),row['id']))
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.database,timeout=20);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def owner(self,cookie=None):
        with self.lock,self.db() as db:
            row=db.execute('SELECT * FROM owners WHERE id=?',(cookie or '',)).fetchone()
            if row:return dict(row),False
            identifier=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
            db.execute('INSERT INTO owners VALUES (?,?,?)',(identifier,csrf,time.time()))
            return {'id':identifier,'csrf':csrf},True
    def authenticate(self,cookie):
        with self.db() as db:row=db.execute('SELECT * FROM owners WHERE id=?',(cookie or '',)).fetchone()
        if not row:raise ServiceError('session_required','请刷新页面建立本机会话。',401)
        return dict(row)
    def _session(self,owner,sid):
        with self.db() as db:row=db.execute('SELECT * FROM sessions WHERE id=? AND owner=?',(sid,owner)).fetchone()
        if not row:raise ServiceError('not_found','会话或运行不存在。',404)
        result=dict(row);result['documents']=json.loads(result['documents']);return result
    def create_session(self,owner,title='新对话'):
        with self.lock,self.db() as db:
            if db.execute('SELECT count(*) FROM sessions WHERE owner=?',(owner,)).fetchone()[0]>=50:raise ServiceError('session_limit','当前浏览器最多保留50个会话。',409)
            sid=uuid.uuid4().hex
            db.execute('INSERT INTO sessions VALUES (?,?,?,?,?)',(sid,owner,title[:60],now(),'{}'))
        return self.session(owner,sid)
    def sessions(self,owner):
        with self.db() as db:rows=db.execute('SELECT id,title,created FROM sessions WHERE owner=? ORDER BY created DESC',(owner,)).fetchall()
        return [{'session_id':r['id'],'title':r['title'],'created_at':r['created']} for r in rows]
    def entries(self,sid):
        with self.db() as db:rows=db.execute('SELECT data FROM runs WHERE session_id=? ORDER BY rowid',(sid,)).fetchall()
        return [json.loads(row['data']) for row in rows]
    def _entry(self,sid,rid):
        with self.db() as db:row=db.execute('SELECT data FROM runs WHERE id=? AND session_id=?',(rid,sid)).fetchone()
        if not row:raise ServiceError('not_found','会话或运行不存在。',404)
        return json.loads(row['data'])
    def view(self,entry):
        return project_record(entry['record'],entry['session_id'],entry['phase'],entry['canaries'],entry['warnings'])
    def session(self,owner,sid):
        row=self._session(owner,sid)
        with self.db() as db:seq=db.execute('SELECT COALESCE(MAX(sequence),0) FROM events WHERE session_id=?',(sid,)).fetchone()[0]
        return {'session_id':sid,'title':row['title'],'created_at':row['created'],'documents':[metadata(k,v) for k,v in row['documents'].items()],
                'runs':[self.view(e) for e in self.entries(sid)],'last_sequence':seq}
    def run(self,owner,sid,rid):self._session(owner,sid);return self.view(self._entry(sid,rid))
    def upload(self,owner,sid,filename,parsed):
        with self.lock:
            row=self._session(owner,sid)
            if len(row['documents'])>=8:raise ServiceError('document_limit','每个会话最多导入8份文档。',409)
            name=''.join(c for c in filename if c.isprintable())[:100] or '上传资料'
            # A name is display-only; the opaque ID is generated independently.
            identifier='doc_'+uuid.uuid4().hex[:12]
            doc={'name':name,'content':parsed['text'],'source_type':'upload','sensitivity':'internal','warnings':parsed['warnings']}
            row['documents'][identifier]=doc
            with self.db() as db:db.execute('UPDATE sessions SET documents=? WHERE id=?',(encoded(row['documents']),sid))
            return metadata(identifier,doc)
    def add_preview(self,owner,sid,preview):
        self._session(owner,sid);identifier=uuid.uuid4().hex
        with self.db() as db:db.execute('INSERT INTO previews VALUES (?,?,?)',(identifier,sid,encoded(preview)))
        return {'preview_id':identifier,'case_id':preview['case']['id'],'task':preview['case']['runtime']['task'],
                **{k:preview.get(k) for k in ('before','after','fragments','metadata')}}
    def _publish(self,entry):
        sid=entry['session_id'];rid=entry['record']['run_id'];view=self.view(entry)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE runs SET data=? WHERE id=?',(encoded(entry),rid))
            seq=db.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE session_id=?',(sid,)).fetchone()[0]
            event={'session_id':sid,'run_id':rid,'sequence':seq,'phase':entry['phase'],'run':view}
            db.execute('INSERT INTO events VALUES (?,?,?,?)',(sid,seq,rid,encoded(event)))
    def events(self,owner,sid,after):
        self._session(owner,sid)
        with self.db() as db:rows=db.execute('SELECT data FROM events WHERE session_id=? AND sequence>? ORDER BY sequence LIMIT 100',(sid,after)).fetchall()
        return [json.loads(row['data']) for row in rows]
    def _history(self,entries):
        # Import only the most recent complete DAG, which already contains its
        # predecessors. No model-generated self-declared labels are accepted.
        if not entries:return None
        last=entries[-1]['record'];nodes=last.get('nodes',[])
        if len(nodes)>1800:raise ServiceError('history_budget','会话来源链已达预算，请新建对话；旧历史保留。',409)
        parents=[p for group in last.get('_checkpoint',{}).get('visible',[]) for p in group]
        if not nodes or not parents:return None
        text='\n'.join('用户：'+e['record']['task'].partition('\n用户显式选择的文档ID：')[0]+'\n已获准回复：'+e['record'].get('final','') for e in entries[-3:])
        return {'nodes':nodes,'parents':parents,'text':text[-1600:]}
    def start(self,owner,sid,payload):
        with self.lock:
            session=self._session(owner,sid);input_hash=hashlib.sha256(encoded(payload).encode()).hexdigest()
            with self.db() as db:previous=db.execute('SELECT input_hash,data FROM runs WHERE session_id=? AND request_id=?',(sid,payload['request_id'])).fetchone()
            if previous:
                if previous['input_hash']!=input_hash:raise ServiceError('idempotency_conflict','重复请求的内容发生变化，请使用新的请求标识。',409)
                return self.view(json.loads(previous['data']))
            old=self.entries(sid)
            if any(e['record']['status'] in ('running','pending','stopping') for e in old):raise ServiceError('run_active','请先完成确认或停止当前任务。',409)
            if len(old)>=20:raise ServiceError('turn_limit','每个会话最多20轮，请新建对话；旧历史保留。',409)
            case=None;warnings=[]
            if payload.get('preview_id'):
                with self.db() as db:row=db.execute('SELECT data FROM previews WHERE id=? AND session_id=?',(payload['preview_id'],sid)).fetchone()
                if not row:raise ServiceError('preview_missing','预览不存在或不属于此会话。',404)
                preview=json.loads(row['data']);case=preview['case'];runtime=case['runtime'];history=None
                warnings.append('规则生成演示样本；本次单案不计入正式批次。')
            else:
                try:runtime,warnings=create_runtime(payload['task'],payload['document_ids'],payload.get('recipient_id'),payload.get('export_path'),payload['private_mode'],session['documents'])
                except ValueError as e:
                    code=str(e);message={'selection_required_recipient':'请显式选择模拟收件人后发送。','selection_required_export':'请显式选择虚拟导出位置后发送。','private_mode_required':'处理模拟敏感文档需要先启用私有会话授权。'}.get(code,'所选资源不在本机授权目录内。')
                    raise ServiceError('selection_required' if code.startswith('selection_required') else code,message) from None
                history=self._history(old)
            rid=uuid.uuid4().hex;canary='CANARY_'+secrets.token_hex(16)
            canaries=list(dict.fromkeys([c for e in old for c in e['canaries']]+[canary])) if history else [canary]
            record={'run_id':rid,'mode':payload['mode'],'seed':payload['seed'],'status':'running','started_at':now(),'task':runtime['task'],'events':[],'nodes':[],'state':{},'usage':{},'final':''}
            entry={'session_id':sid,'phase':'queued','record':record,'runtime':runtime,'case':case,'canary':canary,'canaries':canaries,'warnings':warnings,'version':'2.0.0'}
            with self.db() as db:
                db.execute('INSERT INTO runs VALUES (?,?,?,?,?)',(rid,sid,payload['request_id'],input_hash,encoded(entry)))
                if len(old)==0:db.execute('UPDATE sessions SET title=? WHERE id=?',(payload['task'][:36] or '攻击实验',sid))
            self.controls[rid]=(threading.Event(),threading.RLock())
            self._publish(entry)
            self.futures[rid]=self.pool.submit(self._work,entry,None,history)
            return self.view(entry)
    def _work(self,entry,approve=None,history=None):
        rid=entry['record']['run_id'];stop,gate=self.controls[rid]
        def observer(phase,record):
            with self.lock:
                entry['record']=copy.deepcopy(record);entry['phase']=phase
                if stop.is_set() and record['status'] in ('running','pending'):entry['record']['status']='stopping'
                self._publish(entry)
        try:
            backend=self.backend_factory()
            kwargs={'observer':observer,'stop_event':stop,'control_lock':gate}
            if approve is None:
                record=run_case(entry['runtime'],entry['record']['mode'],entry['record']['seed'],rid,backend,entry['canary'],'pending',history=history,**kwargs)
            else:record=resume_run(entry['record'],approve,backend,ledger_path=self.directory/'confirmations.sqlite',**kwargs)
            if stop.is_set():record['status']='stopped';record['pending']=None
            # Evaluate the original state, before audit redaction. Free chat has no answer key.
            if entry['case']:
                record['assessment']=evaluate(entry['case'],record,entry['canary'])
                record.update(case_id=entry['case']['id'],kind=entry['case']['kind'],category=entry['case']['category'])
            with self.lock:entry['record']=record;entry['phase']=record['status'];self._publish(entry)
        except Exception:
            with self.lock:
                # Never reflect exception text from model/upload content in an error channel.
                entry['record']['status']='stopped' if stop.is_set() else 'model_error'
                entry['phase']=entry['record']['status'];entry['warnings'].append('任务未能继续，已保留最后的真实状态；没有自动重试副作用。')
                self._publish(entry)
    def stop(self,owner,sid,rid):
        self._session(owner,sid)
        with self.lock:
            entry=self._entry(sid,rid)
            if entry['record']['status'] not in ('running','pending','stopping'):return self.view(entry)
            stop,gate=self.controls.setdefault(rid,(threading.Event(),threading.RLock()))
        # Same lock as dispatch gives Stop a defined linearization boundary.
        with gate:stop.set()
        with self.lock:
            entry=self._entry(sid,rid)
            if entry['record']['status']=='pending':entry['record']['status']='stopped';entry['record']['pending']=None
            elif entry['record']['status']=='running':entry['record']['status']='stopping'
            entry['phase']=entry['record']['status'];self._publish(entry);return self.view(entry)
    def confirm(self,owner,sid,rid,payload):
        with self.lock:
            self._session(owner,sid);entry=self._entry(sid,rid)
            body_hash=hashlib.sha256(encoded(payload).encode()).hexdigest()
            with self.db() as db:old=db.execute('SELECT body_hash FROM confirmation_requests WHERE run_id=? AND request_id=?',(rid,payload['request_id'])).fetchone()
            if old:
                if old['body_hash']!=body_hash:raise ServiceError('idempotency_conflict','同一确认请求内容不能改变。',409)
                return self.view(entry)
            pending=entry['record'].get('pending')
            if entry['record']['status']!='pending' or not pending:raise ServiceError('not_pending','此动作已处理或不在等待确认。',409)
            if not secrets.compare_digest(pending['hash'],payload['action_hash']):raise ServiceError('confirmation_changed','当前动作与页面显示的内容不一致，请刷新。',409)
            if time.time()>pending['expires_at']:raise ServiceError('confirmation_expired','确认已经过期，请停止后重新发起任务。',409)
            with self.db() as db:db.execute('INSERT INTO confirmation_requests VALUES (?,?,?)',(rid,payload['request_id'],body_hash))
            original=copy.deepcopy(entry)
            entry['record']['status']='running';entry['phase']='confirmation_processing';self._publish(entry)
            self.controls.setdefault(rid,(threading.Event(),threading.RLock()))
            self.futures[rid]=self.pool.submit(self._work,original,payload['approve'],None)
            return self.view(entry)
    def export(self,owner,sid,rid,download_id):
        self._session(owner,sid);entry=self._entry(sid,rid);view=self.view(entry)
        item=next((f for f in view['state']['files'] if f.get('download_id')==download_id and download_id),None)
        if not item:raise ServiceError('export_not_authorized','没有可下载的获准虚拟导出物。',404)
        raw_files=entry['record']['state']['files'];path=next((p for p in raw_files if hashlib.sha256(p.encode()).hexdigest()[:20]==download_id),None)
        if not path:raise ServiceError('not_found','导出物不存在。',404)
        return raw_files[path]
    def close(self):
        for event,gate in self.controls.values():
            with gate:event.set()
        self.pool.shutdown(wait=True,cancel_futures=True)
