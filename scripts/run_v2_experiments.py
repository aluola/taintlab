"""Freeze and execute comparable local-model v2 campaigns without touching v1."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
from taintlab.experiments import run_batch,runtime_fingerprint,write_json

ROOT=Path(__file__).resolve().parents[1]
LOCK=ROOT/'configs/experiment_v2.lock.json'
FILES=('data/test.jsonl','data/v2/test.jsonl','data/v2/frozen_manifest.json','configs/model.json','configs/model.lock.json')
def signature():
    return {'version':'2.0.0','runtime_sha256':runtime_fingerprint(),
            'files':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES},
            'modes':['none','input_filter','taint_policy','policy_only'],'seeds':[11,23,47],
            'confirmation_mode':'simulate_authorized','workers':4,'planned_runs':{'baseline':1296,'external':1080},
            'evaluation':'terminal completed + actual state assertions; failures/pending/exhaustion remain denominators'}
def main():
    os.chdir(ROOT)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--freeze',action='store_true');p.add_argument('--campaign',choices=['baseline','external','both'],default='both')
    args=p.parse_args();current=signature()
    if args.freeze:
        if LOCK.exists() and json.loads(LOCK.read_text())['signature']!=current:raise SystemExit('Frozen v2 signature differs. Preserve this campaign and create a new version; no overwrite permitted.')
        if not LOCK.exists():write_json(LOCK,{'frozen_at':datetime.now(timezone.utc).isoformat(),'selection_before_formal_results':True,'signature':current})
        print('Frozen runtime:',current['runtime_sha256']);return
    if not LOCK.exists() or json.loads(LOCK.read_text())['signature']!=current:raise SystemExit('Runtime/data/config not frozen or differs from frozen v2. Review before running.')
    targets=['baseline','external'] if args.campaign=='both' else [args.campaign]
    for target in targets:
        dataset='data/test.jsonl' if target=='baseline' else 'data/v2/test.jsonl'
        run_batch(dataset,'results/v2/'+target,tuple(current['modes']),tuple(current['seeds']),4,confirmation_mode='simulate_authorized')
if __name__=='__main__':main()
