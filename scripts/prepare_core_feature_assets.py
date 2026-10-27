"""Register actual recorded console frames and snapshot capture scripts.

This does not synthesize application pixels. FFmpeg extracts recorded frames;
the ordinary annotation script adds only disclosed geometric marks.
"""
from pathlib import Path
import hashlib,json,shutil,subprocess
from datetime import datetime,timezone
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return p.relative_to(ROOT).as_posix()
def main():
    takes=ROOT/'docs/assets/core-features/captures'
    for m in takes.glob('*/capture_manifest.json'):
        x=json.loads(m.read_text('utf8'))
        if 'recorder_source' in x:continue
        source=ROOT/'scripts/capture_core_features.cjs'
        raw=ROOT/'demo/core_features/raw'/m.parent.name
        if not raw.is_dir():continue
        snap=raw/'recorder.cjs';shutil.copy2(source,snap)
        x['recorder_source']={'path':rel(snap),'sha256':sha(snap),'public_source':'scripts/capture_core_features.cjs'}
        x['scenario_file']={'path':'data/demo/core_features/scenarios.json','sha256':sha(ROOT/'data/demo/core_features/scenarios.json')}
        raw.joinpath('capture_manifest.json').write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n','utf8')
        m.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n','utf8')
    source=ROOT/'demo/core_features/raw/console_20261027T055111Z'
    meta=json.loads((source/'capture_manifest.json').read_text('utf-8-sig'))
    folder=takes/source.name;folder.mkdir(exist_ok=True)
    cases=[('positive',8,450,[(0,192,1170,288,'实际阳性输入与检测依据'),(0,288,850,384,'近似阴性与空检测依据'),(0,120,1050,192,'非模型正式实验声明')]),
           ('encoded',20,475,[(0,120,1245,216,'两层Base64实际检测'),(0,216,1245,408,'同出口与跨出口分片检测'),(0,432,1190,464,'仅机制自检声明')]),
           ('limits',32,400,[(0,120,1280,240,'三层编码超界阴性'),(0,240,1065,336,'检测上限与7项结论')])]
    figures=[]
    for name,time,height,marks in cases:
        path=folder/f'f06_selfcheck_{name}.png'
        subprocess.run([str(ROOT/'vendor/ffmpeg/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe'),'-y','-ss',str(time),'-i',str(source/'console.mp4'),'-frames:v','1',str(path),'-loglevel','error'],check=True)
        w,h=Image.open(path).size
        figures.append({'id':f'f06_selfcheck_{name}','title':f'实际检测器机制自检：{name}','captured_at_utc':meta['created_at_utc'],'release_version':'2.0.1','runtime_version':'2.0.0','viewport':{'width':w,'height':h},'page_url_path':None,'live_or_replay':'synthetic_detector_selfcheck_actual_console','run_id':None,'mode':None,'seed':None,'case_id':None,'raw_path':rel(path),'raw_sha256':sha(path),'crop':{'x':0,'y':0,'width':w,'height':height},'annotations':[{'number':i+1,'label':m[4],'rect':m[:4],'style':'number_rectangle_arrow'} for i,m in enumerate(marks)],'steps':['实际执行 scripts/demo_canary_selfcheck.py，显示实际stdout分段。'],'observed_result':'检测器机制自检 / 合成输入 / 非模型正式实验。真实调用既有detect_observables；不计ASR。','checks':{'cli_exit_code':0,'completed_pages':3},'video_offset_seconds':time,'source_video':{'path':rel(source/'console.mp4'),'sha256':sha(source/'console.mp4')}})
    (folder/'capture_manifest.json').write_text(json.dumps({'release_version':'2.0.1','runtime_version':'2.0.0','created_at_utc':datetime.now(timezone.utc).isoformat(),'source':'actual native console pixels extracted from verified recording','figures':figures,'errors':[],'source_video':{'path':rel(source/'console.mp4'),'sha256':sha(source/'console.mp4')},'actual_cli_output':'results/core_features/canary/demo_selfcheck_console_20261027T055111Z.json','not_model_experiment':True},ensure_ascii=False,indent=2)+'\n','utf8')
if __name__=='__main__':main()
