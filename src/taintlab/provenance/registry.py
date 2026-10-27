import base64
import hashlib
import uuid
from typing import Literal
from pydantic import BaseModel, ConfigDict

LEVEL = {'public': 0, 'internal': 1, 'secret': 2}

class Node(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    node_id: str
    run_id: str
    source_type: str
    source_id: str
    parent_ids: tuple[str, ...] = ()
    integrity: Literal['trusted_control','untrusted_content']
    sensitivity: Literal['public','internal','secret']
    transformation: str
    dependency_kind: Literal['source','deterministic_data','potential_context']
    content: str
    content_hash: str = ''
    label_basis: str = ''
    origin_run_id: str = ''

class Registry:
    def __init__(self,run_id):
        self.run_id=run_id
        self._nodes={}
    def source(self,content,source_type,source_id,sensitivity='secret',trusted=False):
        return self._add(content,source_type,source_id,(), 'trusted_control' if trusted else 'untrusted_content',sensitivity,'registered_source','source')
    def derive(self,content,parents,transformation='copy',potential=False,source_type='derived'):
        parents=tuple(dict.fromkeys(parents))
        unknown=not parents or any(p not in self._nodes for p in parents)
        sens='secret' if unknown else max((self._nodes[p].sensitivity for p in parents),key=LEVEL.get)
        integrity='untrusted_content' if unknown or potential or any(self._nodes[p].integrity=='untrusted_content' for p in parents) else 'trusted_control'
        return self._add(content,source_type,transformation,parents,integrity,sens,transformation,'potential_context' if potential else 'deterministic_data')
    def _add(self,content,source_type,source_id,parents,integrity,sens,transform,kind):
        basis = '程序控制来源登记' if integrity=='trusted_control' and kind=='source' else ('外部正文无指令权限；敏感度由场景或上传策略登记' if kind=='source' else '保守继承全部父来源的完整性和最高敏感度；模型可见上下文仅表示潜在依赖' if kind=='potential_context' else '确定性派生保留父标签，不降级')
        n=Node(node_id='n_'+uuid.uuid4().hex[:16],run_id=self.run_id,source_type=source_type,source_id=source_id,parent_ids=parents,integrity=integrity,sensitivity=sens,transformation=transform,dependency_kind=kind,content=content,content_hash=hashlib.sha256(content.encode()).hexdigest(),label_basis=basis)
        self._nodes[n.node_id]=n
        return n
    def get(self,node_id):
        return self._nodes[node_id]
    def dump(self):
        return [n.model_dump(mode='json') for n in self._nodes.values()]
    def import_history(self,nodes):
        """Trusted session controller only. Rebind a complete DAG without lowering labels.

        Origin run IDs distinguish prior-turn context from new derivations. This is
        not exposed as a model tool or accepted from browser request payloads.
        """
        for raw in nodes:
            node=Node.model_validate(raw)
            if node.node_id in self._nodes:raise ValueError('duplicate historical node')
            self._nodes[node.node_id]=node.model_copy(update={'run_id':self.run_id,'origin_run_id':node.origin_run_id or node.run_id})
        if any(parent not in self._nodes for node in self._nodes.values() for parent in node.parent_ids):
            raise ValueError('incomplete historical provenance')
    @classmethod
    def restore(cls,run_id,nodes):
        r=cls(run_id)
        r._nodes={n['node_id']:Node.model_validate(n) for n in nodes}
        if any(n.run_id!=run_id for n in r._nodes.values()):
            raise ValueError('cross-run provenance')
        return r
    def transform(self,node_ids,operation,**kwargs):
        content=''.join(self.get(i).content for i in node_ids)
        if operation=='slice': content=content[kwargs.get('start',0):kwargs.get('stop')]
        elif operation=='base64_encode': content=base64.b64encode(content.encode()).decode()
        elif operation=='base64_decode': content=base64.b64decode(content,validate=True).decode()
        elif operation not in ('copy','concat','summary_memory'): raise ValueError('unsupported deterministic operation')
        # summary_memory stores an already bounded verbatim memory; no downgrade rule exists.
        return self.derive(content,node_ids,operation)
