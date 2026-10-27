"""Build a traceable 270-second edit list from actual new recordings.

Every clip references an immutable source and an actual interval. No generated
UI, freeze extension or time stretching. Narration is separate local TTS.
"""
from pathlib import Path
import hashlib,json,subprocess
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'demo/core_features';BIN=ROOT/'vendor/ffmpeg/ffmpeg-9.0.2-essentials_build/bin'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return p.relative_to(ROOT).as_posix()
def load(p):return json.loads(p.read_text('utf-8-sig'))
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n','utf8')
TAKES={'review':'2026-10-27T05-33-38-488Z','tools':'2026-10-27T05-35-28-123Z','attacks':'2026-10-27T05-39-57-717Z','flow':'2026-10-27T05-40-08-159Z','home':'2026-10-27T05-56-12-690Z','upload':'2026-10-27T06-03-17-405Z','console':'console_20261027T055111Z'}
def get_sources():
    sources={}
    for key,folder in TAKES.items():
        m=D/'raw'/folder/'capture_manifest.json';x=load(m)
        v=D/'raw'/folder/'console.mp4' if key=='console' else ROOT/x['source_video']['path']
        probe=load_probe(v);duration=float(probe['format']['duration']);sources[key]={'path':rel(v),'sha256':sha(v),'duration_seconds':duration,'capture_manifest':rel(m),'capture_manifest_sha256':sha(m),'monotonic_seconds':x.get('monotonic_seconds'),'first_ready_seconds':x.get('first_ready_seconds'),'raw_video_public':False,'availability':'Local original take retained for audit; excluded from lightweight release. Recapture with capture_core_features.cjs and update the source mapping for a new production.'}
    return sources
def load_probe(p):return json.loads(subprocess.check_output([str(BIN/'ffprobe.exe'),'-v','error','-show_format','-show_streams','-of','json',str(p)]))
def main():
    sources=get_sources();dump(D/'source_inventory.json',sources)
    qa=D/'qa/alignment';qa.mkdir(parents=True,exist_ok=True)
    for key,at in [('tools',10),('tools',39),('attacks',17),('flow',24),('upload',5),('review',72),('home',5)]:
        p=qa/f'{key}_{at}.png';subprocess.run([str(BIN/'ffmpeg.exe'),'-y','-ss',str(at),'-i',str(ROOT/sources[key]['path']),'-frames:v','1',str(p),'-loglevel','error'],check=True)
    print(json.dumps(sources,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
