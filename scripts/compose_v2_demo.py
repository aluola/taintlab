"""Cut verified real browser footage according to a reproducible edit decision list.

Only recorded frames are selected. No invented UI, frame extension or playback
speed changes. The final encoder adds explicitly identified editorial captions.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/'vendor/ffmpeg/ffmpeg-9.0.2-essentials_build/bin'
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def run(cmd):
    r=subprocess.run([str(v) for v in cmd],capture_output=True)
    if r.returncode:raise RuntimeError(r.stderr.decode('utf8','replace')[-3000:])
    return r.stdout
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('edl',type=Path)
    parser.add_argument('--ffmpeg',type=Path,default=BIN/'ffmpeg.exe')
    parser.add_argument('--ffprobe',type=Path,default=BIN/'ffprobe.exe')
    args=parser.parse_args();plan=json.loads(args.edl.read_text('utf8'))
    if plan['project_version']!='2.0.0':raise ValueError('Expected current version')
    output=(ROOT/plan['output']).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    if not output.is_relative_to(ROOT/'demo/v2'):raise ValueError('Intermediate output must be inside demo/v2')
    command=[args.ffmpeg,'-hide_banner','-y'];filters=[];parts=[];position=0
    for i,cut in enumerate(plan['cuts']):
        source=(ROOT/cut['source']).resolve()
        if source==output or sha(source)!=cut['source_sha256']:raise ValueError('Source hash mismatch')
        probe=json.loads(run([args.ffprobe,'-v','error','-show_format','-show_streams','-of','json',source]))
        start=float(cut['start']);duration=float(cut['duration']);end=start+duration
        if start<0 or duration<=0 or end>float(probe['format']['duration'])+.001:raise ValueError('Cut exceeds actual footage')
        video=next(s for s in probe['streams'] if s['codec_type']=='video')
        if [video['width'],video['height']]!=[1600,900]:raise ValueError('Unexpected source dimensions')
        command+=['-i',source]
        filters.append(f'[{i}:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS,fps=25,setsar=1[v{i}]')
        parts.append({**cut,'output_start':position,'output_end':position+duration,'actual_source_duration':float(probe['format']['duration'])});position+=duration
    if abs(position-240)>.001:raise ValueError('Reviewed current narration requires 240 seconds')
    filters.append(''.join(f'[v{i}]' for i in range(len(parts)))+f'concat=n={len(parts)}:v=1:a=0[v]')
    command+=['-filter_complex',';'.join(filters),'-map','[v]','-an','-c:v','libx264','-preset','veryfast','-crf','16','-pix_fmt','yuv420p',output]
    print('Composing verified real footage without speed changes...',flush=True)
    run(command)
    probe=json.loads(run([args.ffprobe,'-v','error','-show_format','-of','json',output]))
    actual=float(probe['format']['duration'])
    if abs(actual-240)>.06:raise ValueError('Unexpected composed duration')
    manifest={'project_version':'2.0.0','created_at':datetime.now(timezone.utc).isoformat(),'edl_sha256':sha(args.edl),'output':output.relative_to(ROOT).as_posix(),'output_sha256':sha(output),'duration':actual,'cuts':parts,'assurance':'Actual UI recording and explicitly marked actual replay pickups. Navigation waits trimmed; no speed changes, state edits, fabricated frames or artificial extension.'}
    (ROOT/'demo/v2/composition_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf8')
    timing={'project_version':'2.0.0','source_video':output.relative_to(ROOT).as_posix(),'trim_start':0,'duration':240,'overlays':plan['overlays'],'caption_placements':plan.get('caption_placements',[]),'composition_manifest':'demo/v2/composition_manifest.json'}
    (ROOT/'demo/recording_timing.json').write_text(json.dumps(timing,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps({'output':str(output),'duration':actual,'sha256':manifest['output_sha256']},ensure_ascii=False))
if __name__=='__main__':main()
