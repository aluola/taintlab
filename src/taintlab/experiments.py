"""Experiment orchestration. Hidden answers stop here, outside agent/policy modules."""
import csv
import hashlib
import json
import os
import secrets
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from taintlab.agent.runtime import run_case
from taintlab.model.client import LocalModel, load_config

def read_cases(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if line.strip()]

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temp,path)

def runtime_fingerprint():
    files=[]
    for folder in ('agent','model','policy','provenance','tools','evaluation'):
        files.extend(Path('src/taintlab',folder).glob('*.py'))
    files.append(Path(__file__))
    return hashlib.sha256(b''.join(p.read_bytes() for p in sorted(files))).hexdigest()

class RunStore:
    def __init__(self,folder):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        (self.folder/'records').mkdir(exist_ok=True)
        self.db=self.folder/'checkpoints.sqlite'
        with sqlite3.connect(self.db) as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, status TEXT, path TEXT, updated REAL)')
    def save(self,record):
        name=record['run_id']+'.json'
        path=self.folder/'records'/name
        write_json(path,record)
        with sqlite3.connect(self.db,timeout=30) as c:
            c.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?)',(record['run_id'],record['status'],str(path),time.time()))
    def existing(self,run_id):
        path=self.folder/'records'/(run_id+'.json')
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None

def run_batch(dataset='data/test.jsonl',output='results/main',modes=('none','input_filter','taint_policy'),seeds=(11,23,47),workers=4,limit=None,confirmation_mode='simulate_authorized',backend_factory=None):
    from taintlab.evaluation.evaluator import evaluate, summarize
    cases=read_cases(dataset)
    if limit:cases=cases[:limit]
    output=Path(output);store=RunStore(output)
    manifest={'dataset':str(dataset),'dataset_sha256':hashlib.sha256(Path(dataset).read_bytes()).hexdigest(),
              'runtime_version':'2.0.0','evaluation_version':'2.0.0-terminal-completion',
              'model_lock_sha256':hashlib.sha256(Path('configs/model.lock.json').read_bytes()).hexdigest() if Path('configs/model.lock.json').exists() else None,
              'runtime_sha256':runtime_fingerprint(),'model_config':load_config(),'modes':list(modes),'seeds':list(seeds),
              'limit':limit,'confirmation_mode':confirmation_mode,'backend_type':'scripted_test' if backend_factory else 'local_llama_cpp',
              'planned_runs':len(cases)*len(modes)*len(seeds),'workers':workers}
    manifest_path=output/'experiment_manifest.json'
    if manifest_path.exists():
        old=json.loads(manifest_path.read_text(encoding='utf-8'))
        if old!=manifest:raise ValueError('Frozen experiment differs: choose a new results directory; existing evidence is preserved')
    else:write_json(manifest_path,manifest)
    paired_path=output/'paired_scenarios.json'
    pairs=json.loads(paired_path.read_text(encoding='utf-8')) if paired_path.exists() else {}
    for case in cases:
        for seed in seeds:pairs.setdefault(f"{case['id']}:{seed}",'CANARY_'+secrets.token_hex(16))
    write_json(paired_path,pairs)
    jobs=[];records=[]
    for case in cases:
        for seed in seeds:
            for mode in modes:
                # Stable across archive extraction / results-directory relocation.
                run_id=hashlib.sha256((manifest['dataset_sha256']+manifest['runtime_sha256']+case['id']+str(seed)+mode).encode()).hexdigest()[:24]
                old=store.existing(run_id)
                if old:records.append((case,old,pairs[f"{case['id']}:{seed}"]))
                else:jobs.append((case,seed,mode,run_id))
    print(f"planned={manifest['planned_runs']} saved={len(records)} remaining={len(jobs)} backend={manifest['backend_type']}",flush=True)
    def work(job):
        case,seed,mode,run_id=job;canary=pairs[f"{case['id']}:{seed}"]
        rec=run_case(case['runtime'],mode,seed,run_id,backend_factory() if backend_factory else None,canary,confirmation_mode)
        rec.update(case_id=case['id'],kind=case['kind'],category=case['category'],split=case['split'])
        rec['assessment']=evaluate(case,rec,canary)
        store.save(rec)
        return case,rec,canary
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(work,j) for j in jobs]
        for f in as_completed(futures):
            records.append(f.result())
            if len(records)%10==0 or len(records)==manifest['planned_runs']:
                print(f"saved={len(records)}/{manifest['planned_runs']}",flush=True)
    rows=[]
    for case,record,canary in sorted(records,key=lambda x:(x[0]['id'],x[1]['seed'],x[1]['mode'])):
        row=evaluate(case,record,canary)
        row.update(case_id=case['id'],kind=case['kind'],category=case['category'],mode=record['mode'],seed=record['seed'],run_id=record['run_id'])
        rows.append(row)
    (output/'metrics.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    if rows:
        fields=sorted(set().union(*(r.keys() for r in rows)))
        with (output/'metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in row.items()})
    summary=summarize(rows);summary['manifest']=manifest
    write_json(output/'summary.json',summary)
    return summary
