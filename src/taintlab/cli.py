import argparse
import json
from pathlib import Path
from taintlab.experiments import read_cases,write_json,run_batch,RunStore
from taintlab.agent.runtime import run_case

def main():
    p=argparse.ArgumentParser(description='本地小模型 Agent 污点追踪实验平台')
    sub=p.add_subparsers(dest='command',required=True)
    one=sub.add_parser('run');one.add_argument('--dataset',default='data/dev.jsonl');one.add_argument('--case',required=True)
    one.add_argument('--mode',choices=['none','input_filter','taint_policy','policy_only'],default='taint_policy')
    one.add_argument('--seed',type=int,default=11);one.add_argument('--output',default='results/single')
    one.add_argument('--confirmation',choices=['pending','simulate_authorized'],default='pending')
    batch=sub.add_parser('batch');batch.add_argument('--dataset',default='data/test.jsonl');batch.add_argument('--output',default='results/main')
    batch.add_argument('--modes',nargs='+',default=['none','input_filter','taint_policy']);batch.add_argument('--seeds',type=int,nargs='+',default=[11,23,47])
    batch.add_argument('--workers',type=int,default=4);batch.add_argument('--limit',type=int)
    batch.add_argument('--confirmation',choices=['pending','simulate_authorized'],default='simulate_authorized')
    sub.add_parser('generate')
    retry=sub.add_parser('retry',help='Idempotent diagnostic retry; preserve original formal evidence')
    retry.add_argument('--source',required=True);retry.add_argument('--dataset',default='data/test.jsonl')
    retry.add_argument('--output',default='results/retries')
    args=p.parse_args()
    if args.command=='generate':
        from taintlab.attacks.generator import generate_dataset
        generate_dataset()
    elif args.command=='batch':
        result=run_batch(args.dataset,args.output,args.modes,args.seeds,args.workers,args.limit,args.confirmation)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    elif args.command=='retry':
        import hashlib,re
        from taintlab.evaluation.evaluator import evaluate
        old=json.loads(Path(args.source).read_text(encoding='utf-8'))
        rid=hashlib.sha256((old['run_id']+':diagnostic_retry_1').encode()).hexdigest()[:24]
        store=RunStore(args.output)
        if store.existing(rid):
            print('Retry already saved; no new model execution.');return
        case=next(c for c in read_cases(args.dataset) if c['id']==old['case_id'])
        materialized=old['_checkpoint']['runtime']
        matches=re.findall(r'CANARY_[a-f0-9]{32}',json.dumps(materialized))
        if not matches:raise ValueError('Missing paired Canary in saved scene')
        result=run_case(materialized,old['mode'],old['seed'],run_id=rid,canary=matches[0],confirmation_mode=old['confirmation_mode'])
        result.update(case_id=old['case_id'],kind=case['kind'],category=case['category'],retry_of=old['run_id'],diagnostic_retry=True,
                      assessment=evaluate(case,result,matches[0]))
        store.save(result)
        print('Diagnostic retry saved. Original formal metrics remain unchanged: '+rid)
    else:
        import secrets
        from taintlab.evaluation.evaluator import evaluate
        cases=read_cases(args.dataset);case=next((c for c in cases if c['id']==args.case),None)
        if case is None:raise SystemExit(f'Case not found: {args.case}')
        canary='CANARY_'+secrets.token_hex(16)
        result=run_case(case['runtime'],args.mode,args.seed,canary=canary,confirmation_mode=args.confirmation)
        result.update(case_id=case['id'],kind=case['kind'],category=case['category'],assessment=evaluate(case,result,canary))
        path=Path(args.output)/'records'/(result['run_id']+'.json');write_json(path,result)
        print(json.dumps({'path':str(path),'status':result['status'],'assessment':result['assessment']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
