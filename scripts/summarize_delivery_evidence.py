"""Read-only statistics for the delivery process document; no model execution."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]

def summarize_records(records):
    elapsed = sorted(float(r['elapsed_seconds']) for r in records)
    usage = {k: sum(int(r['usage'].get(k, 0)) for r in records) for k in
             ('model_calls', 'model_attempts', 'tool_calls', 'prompt_tokens', 'completion_tokens', 'parse_failures')}
    return {
        'runs': len(records), 'backend_counts': dict(Counter(r['backend_type'] for r in records)),
        'status_counts': dict(Counter(r['status'] for r in records)), 'usage': usage,
        'elapsed_seconds': {'sum_of_record_latencies': sum(elapsed), 'mean': statistics.mean(elapsed),
                            'median': statistics.median(elapsed), 'p95_nearest_rank': elapsed[math.ceil(.95*len(elapsed))-1],
                            'maximum': max(elapsed)},
        'normal_legal_complete': sum(r['kind'] == 'normal' and r['assessment']['legitimate_success'] for r in records),
        'normal_runs': sum(r['kind'] == 'normal' for r in records),
        'confirmation_events': sum(r.get('confirmation_count', 0) for r in records),
    }

def collect(root):
    groups = {}; hashes = {}; all_records = []
    for campaign, expected in (('baseline', 1296), ('external', 1080)):
        files = sorted((root/'results/v2'/campaign/'records').glob('*.json'))
        if len(files) != expected: raise ValueError('Incomplete frozen campaign: ' + campaign)
        records = []
        for path in files:
            payload = path.read_bytes(); record = json.loads(payload)
            if record['backend_type'] != 'local_llama_cpp': raise ValueError('Non-real backend in formal records')
            records.append(record); hashes[path.relative_to(root).as_posix()] = hashlib.sha256(payload).hexdigest()
        groups[campaign] = {mode: summarize_records([r for r in records if r['mode'] == mode])
                            for mode in ('none', 'input_filter', 'taint_policy', 'policy_only')}
        all_records.extend(records)
    return {'kind': 'read_only_aggregation_of_historical_frozen_v2_records',
            'created_at_utc': datetime.now(timezone.utc).isoformat(), 'release_version': '2.0.1',
            'runtime_core_version': '2.0.0', 'new_model_calls': 0, 'formal_records_modified': False,
            'interpretation': 'Per-run elapsed_seconds are saved observation latencies, not total wall-clock time or controlled performance comparisons. P95 is nearest rank. Run terminal completed is distinct from legitimate_success.',
            'campaigns': groups, 'total': summarize_records(all_records),
            'source_records_sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
            'source_file_count': len(hashes)}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--output', type=Path, default=ROOT/'results/core_features/formal_summary.json')
    args = p.parse_args(); report = collect(args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'records': report['source_file_count'], 'new_model_calls': 0, 'total': report['total']}, ensure_ascii=False))

if __name__ == '__main__': main()
