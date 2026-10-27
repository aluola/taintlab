"""Compose only declared intervals of real UI/console recordings, without retiming."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'demo/core_features';BIN=ROOT/'vendor/ffmpeg/ffmpeg-9.0.2-essentials_build/bin'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n','utf8')
def ev(p):return {'path':p,'sha256':sha(ROOT/p)}
def make_plan():
    sources=json.loads((D/'source_inventory.json').read_text('utf8'))
    # Key, source start, duration, chapter, exact visible event.
    raw=[('home',3,10,'INTRO','本地模型配置与真实界面'),
         ('tools',5.8,8,'F01','真实读取动作'),('tools',15,8,'F01','真实查询动作'),('tools',29.5,15,'F01','通知pending、点击确认、真实收件箱'),('tools',58.2,10,'F01','确认导出、实际点击下载'),('attacks',16,4,'F01','实际攻击提出vault读取并被拒'),
         ('upload',3,35,'F02','本轮上传81665601：登记、勾选、实际读取、来源与父链'),
         ('review',19.6,8,'F03','同一正常失败02e896c7真实回放'),('flow',4.6,37,'F03','重新打开同一真实记录，flow拒绝、动作、上游、空状态与失败断言'),
         ('tools',26.6,8,'F04','同一通知pending绑定复看'),('tools',34,11,'F04','同一通知确认操作与收件箱复看'),('tools',45,6,'F04','实际授权与额度'),('tools',94.8,10,'F04','独立6924078b实际点击拒绝且无副作用'),('review',50.2,5,'F04','direct_11越权收件人直接拒绝的真实回放'),
         ('attacks',1.8,5,'F05','直接模板真实生成预览'),('attacks',14.8,5,'F05','直接模板实际运行结果'),('attacks',21.5,5,'F05','间接模板真实生成预览'),('attacks',32,5,'F05','间接模板实际读取结果'),('attacks',38.7,5,'F05','编码模板真实生成预览'),('attacks',49,5,'F05','编码模板实际读取结果'),('attacks',55.8,9,'F05','分段模板两来源预览并实际点击运行'),('attacks',66,6,'F05','分段模板仅读patch的实际结果'),
         ('flow',35.7,5,'F06','真实记录Canary状态，敏感读取不等于泄露'),('console',4,8,'F06','实际检测器合成阳性/阴性自检'),('console',17,7,'F06','实际两层编码与分片自检'),('console',29,4,'F06','实际三层编码覆盖边界'),('review',62.6,6,'F06','当前正式基线三配置次数与分母'),('review',70.4,6,'F06','当前扩展三配置及消融，34/180'),('review',78.2,4,'F06','当前自动和辅助完成拆分'),('home',3,10,'OUTRO','同一首页录制片段作为结束页，非新增运行')]
    clips=[];cursor=0
    for i,(key,start,duration,chapter,description) in enumerate(raw):
        source=sources[key];assert start+duration<=source['duration_seconds']
        clips.append({'index':i,'source_key':key,'source_path':source['path'],'source_sha256':source['sha256'],'source_start_seconds':start,'duration_seconds':duration,'output_start_seconds':cursor,'output_end_seconds':cursor+duration,'chapter':chapter,'description':description,'kind':'synthetic_detector_selfcheck' if key=='console' else 'real_record_replay' if key in ['review','flow'] else 'actual_ui_recording','crop':[0,0,1740,480] if key=='console' else None,'speed':1.0,'freeze_extension':False});cursor+=duration
    assert cursor==270
    records={
      'F01':['0067a37dafcc42a596d3aaddafb82c5a','9d78bb66a8e946e78c0c91fae6e74774','e3a863e65ed147c497279253555f423f','7c0b679ff6144abf9fb16222052d108e','13e8e74e39964b0d86cbb802f7d7ed56'],
      'F02':['81665601dc9c4c77bbc372817e24fdcc'],
      'F03':['02e896c79a27f017d77ac413'],
      'F04':['e3a863e65ed147c497279253555f423f_pending','e3a863e65ed147c497279253555f423f','6924078b8cf046c5b73c7098835a196e','b727ecd1317c41711cd49c98'],
      'F05':['13e8e74e39964b0d86cbb802f7d7ed56','fea661ce276242058e9db166f7cb07a2','f669a5e3fb324d6cb911480de1ccdca4','adcc853ff57c476b9c896b49d523be18'],
      'F06':['02e896c79a27f017d77ac413']}
    chapters=[]
    for ch in records:
        cc=[c for c in clips if c['chapter']==ch]
        keys=list(dict.fromkeys(c['source_key'] for c in cc))
        op=[ev('docs/assets/core-features/captures/'+Path(sources[k]['capture_manifest']).parent.name+'/capture_manifest.json') for k in keys]
        rr=[ev('results/core_features/demo_runs/'+r+'.json') for r in records[ch]]
        if ch=='F06':rr+=[ev('results/core_features/canary/demo_selfcheck_console_20261027T055111Z.json'),ev('results/v2/baseline/summary.json'),ev('results/v2/external/summary.json')]
        chapters.append({'id':ch,'start_seconds':cc[0]['output_start_seconds'],'end_seconds':cc[-1]['output_end_seconds'],'operation_evidence':op,'result_evidence':rr})
    plan={'project_version':'2.0.0','runtime_version':'2.0.0','release_version':'2.0.1','created_at_utc':datetime.now(timezone.utc).isoformat(),'duration_seconds':270,'clips':clips,'feature_chapters':chapters,'sources':sources,'disclosure':['Actual browser and native console video only. Waiting intervals cut; speed1.0. No UI injection, generated results or freeze extension.','F04 revisits the same F01 confirmation recording with its same run ID; intro/outro reuse the same actual home shot.','F03 two captures reopen the same immutable real normal-failure record, not different executions.','All new actual model runs remain outside formal metrics. Source videos remain local raw evidence; public manifests retain hashes.']}
    dump(D/'edit_decisions.json',plan)
    selection={'version':'2.0.0','runtime_version':'2.0.0','release_version':'2.0.1','formal_experiment':False,'features':chapters,'records':[x for ch in chapters for x in ch['result_evidence']]};dump(D/'selection.json',selection)
    selected={'version':'2.0.0','project_version':'2.0.0','release_version':'2.0.1','records':list({x['path']:x for x in selection['records'] if 'demo_runs/' in x['path']}.values())};dump(ROOT/'demo/selected_evidence.json',selected)
    rec=D/'recordings';rec.mkdir(exist_ok=True)
    for key,source in sources.items():
        x=json.loads((ROOT/source['capture_manifest']).read_text('utf-8-sig'));x.update({'version':'2.0.0','project_version':'2.0.0','runtime_version':'2.0.0','release_version':'2.0.1','selection_file':'demo/core_features/selection.json','selection_sha256':sha(D/'selection.json'),'upload_file':'data/demo/core_features/external_handover.txt','upload_sha256':sha(ROOT/'data/demo/core_features/external_handover.txt'),'source_video':source,'raw_video_public':False})
        dump(rec/(key+'.json'),x)
    return plan
def main():
    plan=make_plan()
    if '--plan-only' in sys.argv:return
    out=D/'intermediate';out.mkdir(exist_ok=True)
    for c in plan['clips']:
        source=ROOT/c['source_path'];assert sha(source)==c['source_sha256']
        target=out/f"clip_{c['index']:02}.mp4"
        filters=[]
        if c['crop']:
            x,y,w,h=c['crop'];filters.append(f'crop={w}:{h}:{x}:{y}')
        filters+=['scale=1600:900:force_original_aspect_ratio=decrease','pad=1600:900:(ow-iw)/2:(oh-ih)/2:color=white','setsar=1','setpts=PTS-STARTPTS','fps=30']
        cmd=[str(BIN/'ffmpeg.exe'),'-y','-ss',str(c['source_start_seconds']),'-i',str(source),'-t',str(c['duration_seconds']),'-an','-vf',','.join(filters),'-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-loglevel','error',str(target)]
        subprocess.run(cmd,check=True);print(f"clip {c['index']} {c['chapter']}",flush=True)
    listing=out/'concat.txt';listing.write_text(''.join(f"file 'clip_{c['index']:02}.mp4'\n" for c in plan['clips']),'utf8')
    target=D/'composed.mp4'
    subprocess.run([str(BIN/'ffmpeg.exe'),'-y','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart','-loglevel','error',str(target)],check=True)
    dump(D/'composition_manifest.json',{'project_version':'2.0.0','runtime_version':'2.0.0','release_version':'2.0.1','created_at_utc':datetime.now(timezone.utc).isoformat(),'edl_path':'demo/core_features/edit_decisions.json','edl_sha256':sha(D/'edit_decisions.json'),'output':'demo/core_features/composed.mp4','output_sha256':sha(target),'duration_seconds':270,'all_clips_real_recorded_intervals':True,'no_retiming_or_extension':True})
if __name__=='__main__':main()
