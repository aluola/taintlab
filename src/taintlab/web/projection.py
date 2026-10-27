"""Audit projection. Evaluate original simulated outputs BEFORE applying this view.

The browser is not an unrestricted dump of a checkpoint. Content is disclosed
only when its program label fits the run's authorized viewer. This common host
isolation is never counted as experimental defense effectiveness.
"""
from __future__ import annotations
import base64
import hashlib
import json
from functools import lru_cache
from urllib.parse import quote
from taintlab.provenance.registry import LEVEL
from taintlab.evaluation.canary import detect_observables, normalize, _decoded, MAX_TEXT, MAX_ITEMS, MAX_DEPTH, MAX_CANDIDATES
from taintlab.evaluation.evaluator import _observable_sinks

REASONS={
 'baseline_no_application_policy':'当前基线未启用应用权限和信息流阻断',
 'task_grant_and_flow_passed':'通过任务授权及适用的信息流检查',
 'document_not_granted':'读取对象不在本任务授权范围', 'recipient_not_granted':'收件人不在本任务白名单',
 'path_not_granted':'虚拟路径不在本任务白名单','format_not_granted':'未授权的导出格式',
 'sensitivity_flow_denied':'上下文标签高于目标允许的敏感度', 'tool_not_granted':'工具不在本任务授权范围',
 'human_confirmation_required':'权限范围内的副作用需要人工确认','human_rejected':'用户拒绝了该动作',
 'confirmation_invalid':'确认已失效或已使用','already_executed':'动作已经执行，拒绝重复确认',
 'idempotent_replay':'已执行动作的幂等回执，没有重复副作用','quota_exceeded':'本任务工具调用额度已用尽',
 'grant_expired_or_wrong_run':'授权过期或不属于当前运行','unknown_object':'未知模拟资源',
 'overwrite_not_granted':'不允许覆盖已导出的虚拟文件','invalid_model_json':'模型动作格式无效',
 'ContextBudgetError':'模型上下文预算不足，请减少本次资料或新建对话',
}

@lru_cache(maxsize=256)
def _audit_fragments(canary):
    """Bounded audit-only redaction, not an experimental security policy.

    Six-character recognizable fragments are hidden to prevent normal split
    delivery through several cards. This is deliberately conservative and does
    not claim protection against arbitrary ciphers or shorter side channels.
    """
    variants={canary,base64.b64encode(canary.encode()).decode(),canary.encode().hex(),quote(canary,safe='')}
    variants |= {base64.b64encode(v.encode()).decode() for v in list(variants)}
    return frozenset(v[i:i+6] for v in variants for i in range(max(0,len(v)-5)))


def mask(value,canaries):
    if isinstance(value,dict):return {str(mask(k,canaries)):mask(v,canaries) for k,v in value.items()}
    if isinstance(value,list):return [mask(v,canaries) for v in value]
    if not isinstance(value,str):return value
    fragments=set().union(*(_audit_fragments(c) for c in canaries if c)) if canaries else set()
    if not fragments:return value
    queue=[(value[:MAX_TEXT],0)];seen=set()
    while queue and len(seen)<MAX_CANDIDATES:
        candidate,depth=queue.pop(0);candidate=normalize(candidate)
        if candidate in seen:continue
        seen.add(candidate)
        if any(candidate[i:i+6] in fragments for i in range(max(0,len(candidate)-5))):
            return '[模拟Canary及可识别分片已遮蔽]'
        if depth<MAX_DEPTH:
            for _,decoded in _decoded(candidate):
                queue.append((decoded,depth+1))
                if len(queue)+len(seen)>=MAX_CANDIDATES:break
    return value

def canary_report(record,canaries):
    state=record.get('state',{});grant=record.get('grant',{})
    findings=[]
    for c in canaries:
        findings.extend(detect_observables(_observable_sinks(state,grant),c)['findings'])
    for finding in findings:
        # Model-controlled filenames/recipients must not become an audit escape.
        channel=finding['sink'].partition(':')[0]
        finding['sink']=channel if channel in ('notification','export','final','search_query','observable_error','notification_metadata','file_metadata','unauthorized_observer_coalition') else 'unauthorized_sink'
    nodes={n['node_id']:n for n in record.get('nodes',[])}
    blocked=sum(e.get('decision')=='block' and nodes.get(e.get('node_id'),{}).get('sensitivity')=='secret' and
                (e.get('action') or {}).get('tool')!='read_document' for e in record.get('events',[]))
    terminal=record.get('status') not in ('running','pending','stopping')
    return {'established':bool(canaries),'read':'vault' in state.get('reads',[]),'status':'发现泄露' if findings else '未发现' if terminal else '未运行/检查不完整',
            'findings':mask(findings,canaries),'attempts_blocked':blocked,'authorized_sensitive_read':'vault' in state.get('reads',[]) and 'vault' in grant.get('readable_docs',[]),
            'limits':{'max_text':MAX_TEXT,'max_items':MAX_ITEMS,'max_depth':MAX_DEPTH,'max_candidates':MAX_CANDIDATES},
            'scope':'原始模拟状态先检测，再遮蔽审计视图；有界规范化/编码/同运行分段，不覆盖任意密码与侧信道'}

def project_record(record,session_id='',phase='',canaries=(),warnings=(),historical=False,version='2.0.0'):
    grant=record.get('grant',{});ceiling=1 if historical else LEVEL.get(grant.get('reply_sensitivity','internal'),1)
    nodes={n['node_id']:n for n in record.get('nodes',[])}
    def allowed(node):return node is not None and LEVEL.get(node.get('sensitivity'),2)<=ceiling
    def clean(value):return mask(value,canaries)
    events=[]
    approved_nodes=set()
    for event in record.get('events',[]):
        action=event.get('action') or {};node=nodes.get(event.get('node_id'));disclose=allowed(node)
        arguments=action.get('arguments',{}) if disclose else {'内容':'[敏感上下文参数未向此出口展示]'}
        if action.get('type')=='final':arguments={'content':action.get('content','')} if disclose and event.get('decision')=='allow' else {}
        source_ids=list(node.get('parent_ids',[])) if node else []
        tool=action.get('tool',action.get('type','system'))
        if tool not in ('read_document','search_info','send_notification','export_file','final','system'):tool='system'
        reason=event.get('reason','unknown')
        if reason not in REASONS and reason not in ('HTTPStatusError','ConnectError','ReadError','RuntimeError','KeyError','StopIteration'):reason='unknown'
        events.append({'step':event.get('step',0),'tool':tool,'decision':event.get('decision','error'),'reason':reason,
                       'reason_text':REASONS.get(reason,'模型或服务请求失败，未获准的新副作用不会执行'),
                       'node_id':event.get('node_id',''),'summary':clean(str(next(iter(arguments.values()),'')))[:110],
                       'arguments':clean(arguments),'result_summary':'工具执行已有真实回执' if event.get('decision')=='allow' else REASONS.get(reason,'操作未获准'),
                       'source_ids':source_ids,'confirmation_actor':event.get('confirmation_actor')})
        if event.get('decision')=='allow':approved_nodes.add(event.get('node_id'))
    sources=[]
    for node in nodes.values():
        item={k:node.get(k) for k in ('node_id','source_id','source_type','integrity','sensitivity','parent_ids','transformation','dependency_kind','origin_run_id')}
        item.update(display_name=node.get('source_id','来源'),content_hash=node.get('content_hash') or hashlib.sha256(node.get('content','').encode()).hexdigest(),
                    label_basis=node.get('label_basis') or '历史版本来源登记：正文不拥有指令权限；派生保守继承标签')
        if node.get('dependency_kind')=='source' and node.get('source_type') not in ('system','task_grant') and allowed(node):
            # Do not disclose an unselected sensitive source through the audit sidebar.
            if node.get('source_type') not in ('document','upload') or node.get('source_id') in grant.get('readable_docs',[]):item['preview']=clean(node.get('content','')[:800])
        sources.append(item)
    final_event=next((e for e in reversed(record.get('events',[])) if (e.get('action') or {}).get('type')=='final' and e.get('decision')=='allow'),None)
    final=clean(record.get('final','')) if final_event and allowed(nodes.get(final_event.get('node_id'))) else ('[最终内容的敏感度超出当前审计出口，已隐藏；原始模拟状态仍参与评测]' if record.get('final') else '')
    state=record.get('state',{});inbox=[];files=[]
    def action_node(tool,target,key):
        return next((nodes.get(e.get('node_id')) for e in reversed(record.get('events',[])) if e.get('decision')=='allow' and (e.get('action') or {}).get('tool')==tool and (e['action'].get('arguments') or {}).get(key)==target),None)
    for item in state.get('inbox',[]):
        node=action_node('send_notification',item['recipient_id'],'recipient_id')
        inbox.append({'recipient_id':clean(item['recipient_id']) if allowed(node) else '[敏感目标已隐藏]',
                      'body':clean(item['body']) if allowed(node) else '[正文敏感度超出审计出口，已隐藏]'})
    for path,content in state.get('files',{}).items():
        node=action_node('export_file',path,'path');safe=allowed(node)
        authorized=path in grant.get('export_paths',{}) and node and LEVEL.get(node.get('sensitivity'),2)<=LEVEL[grant['export_paths'][path]]
        files.append({'path':clean(path) if safe else '[敏感路径已隐藏]','content':clean(content) if safe else '[导出内容已隐藏]',
                      'download_id':hashlib.sha256(path.encode()).hexdigest()[:20] if safe and authorized and not historical else None})
    p=record.get('pending');pending=None
    if p and record.get('status')=='pending' and not historical:
        node=nodes.get(p.get('node_id'));action=p['action'];a=action['arguments']
        pending={'action_hash':p['hash'],'tool':action['tool'],'target':clean(a.get('recipient_id',a.get('path',''))) if allowed(node) else '[敏感目标]',
                 'preview':clean(a.get('body',a.get('content',''))) if allowed(node) else '[当前出口无权查看敏感正文]',
                 'expires_at':p['expires_at'],'node_id':p['node_id'],'source_ids':list(node.get('parent_ids',[])) if node else [],
                 'risk_reason':'动作已通过权限检查，尚未执行；确认只批准当前目标与内容，不扩大授权。'}
    used=record.get('_checkpoint',{}).get('gateway_attempts',record.get('usage',{}).get('tool_calls',0))
    queries=[]
    for query in state.get('search_queries',[]):
        node=action_node('search_info',query,'query');queries.append(clean(query) if allowed(node) else '[敏感查询已隐藏]')
    assessment=record.get('assessment')
    assessment_view={k:v for k,v in (assessment or {}).items() if isinstance(v,(bool,int,float)) or k in ('status','backend_type','confirmation_mode')}
    if assessment:
        assessment_view.update({k+'_count':len(assessment.get(k,[])) for k in ('unauthorized_reads','unauthorized_recipients','unauthorized_paths')})
    return {'run_id':record.get('run_id'),'session_id':session_id,'version':version,'mode':record.get('mode'),'seed':record.get('seed'),
            'backend_type':record.get('backend_type','not_started'),
            'task':clean(record.get('task','').partition('\n用户显式选择的文档ID：')[0]),'status':record.get('status','running'),'phase':phase,
            'final':final,'created_at':record.get('started_at'),'historical':historical,'events':events,'sources':sources,
            'grant':{**grant,'policy_version':'gateway-2.0' if version=='2.0.0' else '未记录（历史版）','used_calls':used,'remaining_calls':max(0,grant.get('max_tool_calls',6)-used)},
            'pending':pending,'state':{'reads':state.get('reads',[]),'inbox':inbox,'files':files,'search_queries':queries},
            'canary':canary_report(record,canaries),'evaluation':{'status':'已按预设断言评定','details':assessment_view} if assessment else {'status':'未自动评定','details':{'reason':'自由对话没有预设答案；不纳入正式任务完成率'}},
            'usage':record.get('usage',{}),'warnings':list(warnings)}
