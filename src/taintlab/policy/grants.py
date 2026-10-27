import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Sensitivity=Literal['public','internal','secret']
class TaskGrant(BaseModel):
    model_config=ConfigDict(frozen=True,extra='forbid')
    task_id: str
    run_id: str
    tools: tuple[str,...]
    readable_docs: tuple[str,...]
    recipients: dict[str,Sensitivity]
    export_paths: dict[str,Sensitivity]
    reply_sensitivity: Sensitivity='internal'
    query_sensitivity: Sensitivity='internal'
    max_tool_calls: int=Field(default=6,ge=1,le=6)
    confirm_tools: tuple[str,...]=()
    ttl_seconds: int=3600
    issued_at: float
    expires_at: float

    @classmethod
    def bind(cls,raw,run_id):
        raw=dict(raw)
        now=time.time()
        raw.update(task_id=run_id,run_id=run_id,issued_at=now,expires_at=now+raw.get('ttl_seconds',3600))
        return cls.model_validate(raw)

def canonical_hash(run_id,action):
    value=json.dumps({'run_id':run_id,'action':action},ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(value.encode()).hexdigest()

class Confirmations:
    """A token is minted only by a trusted UI/experiment controller method."""
    def __init__(self):
        self.pending={}
        self.tokens={}
        self.executed=set()
    def request(self,run_id,action,node_id,now=None):
        now=time.time() if now is None else now
        digest=canonical_hash(run_id,action)
        self.pending[digest]={'run_id':run_id,'action':action,'node_id':node_id,'hash':digest,'expires_at':now+300}
        return self.pending[digest]
    def approve(self,digest,run_id,now=None):
        now=time.time() if now is None else now
        p=self.pending.get(digest)
        if not p or p['run_id']!=run_id or now>p['expires_at'] or digest in self.executed:
            raise ValueError('invalid or expired confirmation')
        token=secrets.token_urlsafe(24)
        self.tokens[token]={'hash':digest,'run_id':run_id,'expires_at':p['expires_at']}
        return token
    def consume(self,token,run_id,action,now=None):
        now=time.time() if now is None else now
        digest=canonical_hash(run_id,action)
        t=self.tokens.pop(token,None)
        if not t or t['hash']!=digest or t['run_id']!=run_id or now>t['expires_at'] or digest in self.executed:
            return False
        self.executed.add(digest)
        self.pending.pop(digest,None)
        return True
    def dump(self):
        return {'pending':self.pending,'tokens':self.tokens,'executed':sorted(self.executed)}
    @classmethod
    def restore(cls,raw):
        c=cls();c.pending=raw['pending'];c.tokens=raw['tokens'];c.executed=set(raw['executed']);return c

def claim_ui_confirmation(run_id,digest,ledger_path='results/confirmation_ledger.sqlite'):
    """Prevent an old serialized pending checkpoint from being replayed by the UI.

    SQLite uniqueness is the transactional single-use boundary across processes.
    A crash after claiming fails closed and requires a fresh run/confirmation.
    """
    path=Path(ledger_path);path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path,timeout=30) as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS consumed (run_id TEXT, digest TEXT, at REAL, PRIMARY KEY(run_id,digest))')
        try:connection.execute('INSERT INTO consumed VALUES (?,?,?)',(run_id,digest,time.time()))
        except sqlite3.IntegrityError:raise ValueError('Confirmation already consumed by a prior UI request') from None
