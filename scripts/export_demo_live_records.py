"""Export only explicitly recorded demo runs; never export browser/session credentials."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parents[1]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording_manifest',type=Path)
    args=parser.parse_args()
    manifest_path=args.recording_manifest.resolve()
    capture=json.loads(manifest_path.read_text('utf8'))
    if capture.get('status')!='recorded_actual_ui' or capture.get('version')!='2.0.0':
        raise ValueError('A completed real current recording manifest is required')
    ids=capture['real_run_ids']
    out=ROOT/'results/v2/demo_live/records';out.mkdir(parents=True,exist_ok=True)
    selection_path=ROOT/'demo/selected_evidence.json'
    selection=json.loads(selection_path.read_text('utf8'))
    exported=[]
    with sqlite3.connect((ROOT/'results/v2/web_private/sessions.sqlite').as_uri()+'?mode=ro',uri=True) as db:
        for item in ids:
            rid=item if isinstance(item,str) else item['run_id']
            row=db.execute('SELECT data FROM runs WHERE id=?',(rid,)).fetchone()
            if row is None:raise ValueError('Recorded run is not present: '+rid)
            entry=json.loads(row[0]);record=entry['record']
            if record.get('backend_type')!='local_llama_cpp' or record.get('status')!='completed':
                raise ValueError('Only completed real-local demo records may be archived')
            if any(key in record for key in ('owner','csrf','cookie','canaries','confirmation_requests')):
                raise ValueError('Unexpected browser credential or registry fields in runtime record')
            path=out/(rid+'.json')
            payload=json.dumps(record,ensure_ascii=False,indent=2)+'\n'
            if path.exists() and path.read_text('utf8')!=payload:raise ValueError('Existing demo record differs')
            path.write_text(payload,'utf8')
            evidence={'path':path.relative_to(ROOT).as_posix(),'sha256':digest(path),'version':'2.0.0','purpose':'Actual new UI live demonstration; outside formal ASR denominators','backend_type':record['backend_type'],'run_id':rid,'status':record['status']}
            selection['records']=[r for r in selection['records'] if r.get('path')!=evidence['path']]+[evidence]
            exported.append(evidence)
    selection['notes']=[n for n in selection['notes'] if 'will be appended' not in n]
    selection['notes'].append('Live capture records exported from the server runtime record only; no browser/session credential database is redistributed.')
    selection_path.write_text(json.dumps(selection,ensure_ascii=False,indent=2)+'\n','utf8')
    result={'project_version':'2.0.0','created_at':datetime.now(timezone.utc).isoformat(),'recording_manifest':manifest_path.relative_to(ROOT).as_posix(),'recording_manifest_sha256':digest(manifest_path),'formal_experiment':False,'export_scope':'entry.record only; server ownership, CSRF, session registry and confirmation database excluded','records':exported}
    (out.parent/'export_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
