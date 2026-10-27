"""Bind the actual current six-feature media and public production metadata."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'demo/core_features'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text('utf-8-sig'))
def dump(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n','utf8')
def ev(p):return {'file':p.relative_to(ROOT).as_posix(),'sha256':sha(p)}
def main():
    archive=ROOT/'demo/history/v2.0.0_before_core_features_20261027';archive.mkdir(parents=True,exist_ok=True)
    # Previously committed bytes are retained only as clearly labeled historical
    # production files; never used to verify the new video.
    for name in ['narration.json','recording_timing.json','final_recording_metadata.json','selected_evidence.json']:
        dest=archive/name
        if dest.exists():continue
        if name in ['recording_timing.json','final_recording_metadata.json']:
            shutil.copy2(ROOT/'demo'/name,dest)
        else:
            p=subprocess.run(['git','show','HEAD:demo/'+name],cwd=ROOT,capture_output=True)
            if p.returncode==0:dest.write_bytes(p.stdout)
    composition=load(D/'composition_manifest.json')
    composition['edl_sha256']=sha(D/'edit_decisions.json')
    composition['metadata_binding_note']='Final EDL includes portable public operation-evidence paths and local-source availability. Clip pixel intervals and composed output remain exactly the encoded ones.'
    dump(D/'composition_manifest.json',composition)
    voice=ROOT/'demo/voice/core_features/voice.wav';vm=load(voice.parent/'voice_manifest.json')
    dump(D/'narration_synthesis.json',{'project_version':'2.0.0','runtime_version':'2.0.0','release_version':'2.0.1','created_at_utc':datetime.now(timezone.utc).isoformat(),'engine':'Windows System.Speech / Microsoft Huihui Desktop, offline','narration_file':'demo/narration.json','narration_sha256':sha(ROOT/'demo/narration.json'),'subtitle_file':'demo/demo_subtitles.srt','subtitle_sha256':sha(ROOT/'demo/demo_subtitles.srt'),'voice_file':'demo/voice/core_features/voice.wav','voice_sha256':sha(voice),'voice_manifest_sha256':sha(voice.parent/'voice_manifest.json'),'duration_seconds':270,'segments':vm['segments'],'audio_source_public':False,'scope':'Scheduled offline speech synthesis plus exact caption text/timing verification. Does not claim a human full-track listening review.'})
    shutil.copy2(D/'recording_timing.json',ROOT/'demo/recording_timing.json')
    valid=load(ROOT/'demo/video_validation.json');assert valid['valid'] and abs(valid['actual_duration']-270)<.1
    video=ROOT/'demo/demo.mp4';assert valid['video_sha256']==sha(video)
    dump(ROOT/'demo/final_recording_metadata.json',{'project_version':'2.0.0','runtime_version':'2.0.0','release_version':'2.0.1','recorded_metadata_at_utc':datetime.now(timezone.utc).isoformat(),'video':'demo/demo.mp4','video_sha256':sha(video),'video_bytes':video.stat().st_size,'duration_seconds':valid['actual_duration'],'selected_take':'six_core_features_actual_ui_and_native_detector_console','backend_type':'local_llama_cpp; detector_console_is_synthetic_non_model','composition':'demo/core_features/composition_manifest.json','composition_sha256':sha(D/'composition_manifest.json'),'edit_decisions':'demo/core_features/edit_decisions.json','edit_decisions_sha256':sha(D/'edit_decisions.json'),'source_recordings':[ev(p) for p in sorted((D/'recordings').glob('*.json'))],'selected_run_evidence':'demo/selected_evidence.json','selected_run_evidence_sha256':sha(ROOT/'demo/selected_evidence.json'),'visual_review':'demo/core_features/visual_review.json','playback_review':'demo/playback_validation.json','video_validation':'demo/video_validation.json','narration_synthesis':'demo/core_features/narration_synthesis.json','formal_experiment_mutated':False,'historical_video':'demo/history/v2.0.0_before_core_features_20261027/demo.mp4','historical_video_in_light_package':False})
    print(json.dumps({'duration':valid['actual_duration'],'video_sha256':sha(video),'bytes':video.stat().st_size}))
if __name__=='__main__':main()
