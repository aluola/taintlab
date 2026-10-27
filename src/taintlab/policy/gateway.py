import time
from taintlab.model.protocol import ACTION
from taintlab.policy.grants import canonical_hash
from taintlab.provenance.registry import LEVEL
from taintlab.tools.world import virtual_path

MODES=('none','input_filter','taint_policy','policy_only')

class Gateway:
    def __init__(self,mode,grant,world,registry,confirmations):
        if mode not in MODES:raise ValueError('unknown mode')
        self.mode=mode;self.grant=grant;self.world=world;self.registry=registry;self.confirmations=confirmations
        self.attempts=0
        self.executed=set()
    def inspect(self,action,node,confirmation_token=None):
        try: action=ACTION.validate_python(action).model_dump()
        except ValueError:return 'block','invalid_protocol',None
        is_tool=action['type']=='tool_call'
        if is_tool and action['tool']=='read_document' and action['arguments']['doc_id'] not in self.world.documents:
            return 'block','unknown_object',None
        if self.mode in ('none','input_filter'):
            return 'allow','baseline_no_application_policy',None
        g=self.grant
        if node.run_id!=g.run_id or time.time()>g.expires_at:return 'block','grant_expired_or_wrong_run',None
        if is_tool:
            t=action['tool'];a=action['arguments']
            if self.attempts>=g.max_tool_calls:return 'block','quota_exceeded',None
            if t not in g.tools:return 'block','tool_not_granted',None
            if t=='read_document' and a['doc_id'] not in g.readable_docs:return 'block','document_not_granted',None
            if t=='send_notification' and a['recipient_id'] not in g.recipients:return 'block','recipient_not_granted',None
            if t=='export_file':
                if a['path']!=virtual_path(a['path']) or a['path'] not in g.export_paths:
                    return 'block','path_not_granted',None
                if not a['path'].endswith(('.txt','.md','.json','.csv')):return 'block','format_not_granted',None
                if a['path'] in self.world.state['files']:return 'block','overwrite_not_granted',None
        if self.mode=='taint_policy':
            # The whole action inherits potential context dependencies, including tool choice,
            # recipient, filename, search query and final/error-observable control choices.
            ceiling=g.reply_sensitivity if not is_tool else g.query_sensitivity
            if is_tool and action['tool']=='send_notification':ceiling=g.recipients[action['arguments']['recipient_id']]
            if is_tool and action['tool']=='export_file':ceiling=g.export_paths[action['arguments']['path']]
            if LEVEL[node.sensitivity]>LEVEL[ceiling]:return 'block','sensitivity_flow_denied',None
        if is_tool and action['tool'] in g.confirm_tools:
            digest=canonical_hash(g.run_id,action)
            if digest in self.confirmations.executed:return 'block','already_executed',None
            if not confirmation_token:
                return 'pending','human_confirmation_required',self.confirmations.request(g.run_id,action,node.node_id)
            if not self.confirmations.consume(confirmation_token,g.run_id,action):return 'block','confirmation_invalid',None
        return 'allow','task_grant_and_flow_passed',None
    def dispatch(self,action,node,confirmation_token=None):
        decision,reason,pending=self.inspect(action,node,confirmation_token)
        if action.get('type')=='tool_call' and decision!='pending':self.attempts+=1
        if decision!='allow':
            # Error text is a fixed public vocabulary; no rejected content is reflected.
            return {'decision':decision,'reason':reason,'pending':pending,'result':{'ok':False,'error':reason},'sources':[]}
        digest=canonical_hash(self.grant.run_id,action)
        if action['type']=='tool_call' and action['tool'] in ('send_notification','export_file'):
            if digest in self.executed:
                return {'decision':'allow','reason':'idempotent_replay','result':{'ok':True,'already_executed':True},'sources':[]}
            self.executed.add(digest)
        result,sources=self.world.execute(action)
        return {'decision':'allow','reason':reason,'result':result,'sources':sources}
