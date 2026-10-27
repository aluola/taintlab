"""Encode a real browser recording, local narration, and burned-in Chinese captions.

Input video must already contain the entire requested real-time interval. This
script does not fabricate UI frames, extend footage, or modify experiment data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "vendor/ffmpeg/ffmpeg-9.0.2-essentials_build/bin"
FFMPEG = BIN / "ffmpeg.exe"
FFPROBE = BIN / "ffprobe.exe"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def run(command, *, cwd=None, log=None, binary=False):
    result=subprocess.run([str(x) for x in command],cwd=cwd,capture_output=True)
    if log:
        Path(log).write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {result.stderr.decode('utf-8',errors='replace')[-2500:]}")
    return result.stdout if binary else result.stdout.decode("utf-8",errors="replace")


def probe(path):
    return json.loads(run([FFPROBE,"-v","error","-show_format","-show_streams","-of","json",path]))


def seconds(value):
    h,m,s=value.replace(",",".").split(":")
    return int(h)*3600+int(m)*60+float(s)


def ass_time(value):
    units=round(value*100)
    return f"{units//360000}:{units//6000%60:02}:{units//100%60:02}.{units%100:02}"


def wrap_caption(text, max_units):
    """Insert display-only line breaks; preserve every caption character."""
    lines=[]
    for paragraph in text.splitlines():
        current="";units=0.0
        for char in paragraph:
            width=1.0 if unicodedata.east_asian_width(char) in ("W","F") else 0.6
            if current and units+width>max_units:
                lines.append(current);current="";units=0.0
            current+=char;units+=width
        if current:
            if lines and all(unicodedata.category(char).startswith("P") for char in current):
                lines[-1]+=current
            else:
                lines.append(current)
    return r"\N".join(lines)


def captions_to_ass(srt_path, destination, width, height, duration, annotations=None, placements=None):
    text=Path(srt_path).read_text(encoding="utf-8-sig").replace("\r\n","\n").strip()
    entries=[]
    for block in re.split(r"\n\s*\n",text):
        lines=block.splitlines()
        timing_index=next((i for i,line in enumerate(lines) if " --> " in line),None)
        if timing_index is None:
            raise ValueError("Invalid SRT block: no time interval")
        match=re.fullmatch(r"\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*",lines[timing_index])
        if not match:
            raise ValueError("SRT timing must use HH:MM:SS,mmm")
        start,end=map(seconds,match.groups())
        caption="\n".join(lines[timing_index+1:]).strip()
        if not caption or start<0 or end<=start or end>duration+0.02:
            raise ValueError("Subtitle text or interval is invalid for this video")
        if entries and start<entries[-1]["end"]-0.01:
            raise ValueError("Overlapping captions are not supported")
        if "{" in caption or "}" in caption or "\\" in caption:
            raise ValueError("Subtitle contains ASS control characters; replace with readable plain text")
        entries.append({"start":start,"end":end,"text":caption})
    if len(entries)<2:
        raise ValueError("At least two timed captions are required")
    font_size=round(height*0.038)
    margin=round(width*0.055)
    header=f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,{font_size},&H00FFFFFF,&H000000FF,&H70000000,&H70000000,0,0,0,0,100,100,0,0,3,2,0,2,{margin},{margin},{round(height*0.032)},1
Style: ReplayNotice,Microsoft YaHei,{round(height*0.034)},&H00FFFFFF,&H000000FF,&H40000000,&H40000000,-1,0,0,0,100,100,0,0,3,4,0,8,{margin},{margin},{round(height*0.022)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    max_units=(width-2*margin)/font_size*0.92
    positions=[]
    for p in placements or []:
        start=float(p['start']);end=float(p['end']);y=int(p['top_y'])
        if not 0<=start<end<=duration or not 0<=y<height-100:raise ValueError('Invalid caption placement')
        if positions and start<positions[-1]['end']:raise ValueError('Overlapping caption placements')
        positions.append({'start':start,'end':end,'top_y':y})
    lines=[]
    for e in entries:
        boundaries=sorted({e['start'],e['end']} | {t for p in positions for t in (p['start'],p['end']) if e['start']<t<e['end']})
        for start,end in zip(boundaries,boundaries[1:]):
            placement=next((p for p in positions if p['start']<=start and end<=p['end']),None)
            prefix=(r'{\an8\pos('+str(width//2)+','+str(placement['top_y'])+')}' if placement else '')
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,"+prefix+wrap_caption(e['text'],max_units))
    dialogue='\n'.join(lines)
    for annotation in annotations or []:
        start=float(annotation["start"]);end=float(annotation["end"]);text=str(annotation["text"])
        if start<0 or end<=start or end>duration or any(c in text for c in "{}\\"):
            raise ValueError("Invalid fixed replay annotation")
        dialogue+=f"\nDialogue: 1,{ass_time(start)},{ass_time(end)},ReplayNotice,,0,0,0,,"+wrap_caption(text,max_units)
    destination.write_text(header+dialogue+"\n",encoding="utf-8-sig")
    return entries


def gray_sample(path, at):
    pixels=run([FFMPEG,"-v","error","-ss",f"{at:.3f}","-i",path,"-frames:v","1","-vf","scale=160:90","-pix_fmt","gray","-f","rawvideo","-"],binary=True)
    if len(pixels)!=160*90:
        raise RuntimeError("Could not decode a complete QA video frame")
    return {"time":at,"sha256":hashlib.sha256(pixels).hexdigest(),"mean_luma":round(statistics.mean(pixels),3),"luma_variance":round(statistics.pvariance(pixels),3)}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_webm",type=Path)
    parser.add_argument("--timing",type=Path,default=ROOT/"demo/recording_timing.json")
    parser.add_argument("--voice",type=Path,default=ROOT/"demo/voice/voice.wav")
    parser.add_argument("--subtitles",type=Path,default=ROOT/"demo/demo_subtitles.srt")
    parser.add_argument("--output",type=Path,default=ROOT/"demo/demo.mp4")
    parser.add_argument("--qa-dir",type=Path,help="Versioned QA directory inside the final video's directory")
    parser.add_argument("--project-version",default=None)
    parser.add_argument("--width",type=int,default=1600)
    parser.add_argument("--height",type=int,default=900)
    args=parser.parse_args()
    if (args.width,args.height) not in ((1600,900),(1920,1080)):
        raise ValueError("Use 1600x900 or 1920x1080 for the deliverable")
    raw=args.raw_webm.resolve();voice=args.voice.resolve();subs=args.subtitles.resolve();output=args.output.resolve()
    if raw==output:
        raise ValueError("Output must not overwrite the raw recording")
    output.parent.mkdir(parents=True,exist_ok=True)
    qa=(args.qa_dir or output.parent/"qa").resolve()
    if not qa.is_relative_to(output.parent):raise ValueError("QA directory must remain inside the video directory")
    qa.mkdir(parents=True,exist_ok=True)
    timing=json.loads(args.timing.read_text(encoding="utf-8-sig"))
    if timing.get("source_video") and (ROOT/Path(timing["source_video"])).resolve()!=raw:
        raise ValueError("The supplied raw recording does not match recording_timing.json source_video")
    trim=float(timing["trim_start"]);duration=float(timing.get("duration",240))
    if trim<0 or not 180<=duration<=300:
        raise ValueError("Invalid trim or requested duration outside 180-300 seconds")
    source_probe=probe(raw);voice_probe=probe(voice)
    source_duration=float(source_probe["format"]["duration"])
    voice_duration=float(voice_probe["format"]["duration"])
    if source_duration+0.10<trim+duration:
        raise ValueError(f"Real recording is too short: {source_duration}s for trim={trim}, duration={duration}")
    if abs(voice_duration-duration)>0.1:
        raise ValueError("Narration track duration must match requested video duration")
    if not any(s["codec_type"]=="video" for s in source_probe["streams"]):
        raise ValueError("No video stream in raw recording")
    captions=captions_to_ass(subs,qa/"subtitles.ass",args.width,args.height,duration,timing.get("overlays",[]),timing.get('caption_placements',[]))
    voice_alignment=None
    voice_manifest_path=voice.parent/"voice_manifest.json"
    if voice_manifest_path.exists():
        voice_manifest=json.loads(voice_manifest_path.read_text(encoding="utf-8-sig"))
        segments=voice_manifest.get("segments",[])
        voice_alignment={"manifest_sha256":sha256(voice_manifest_path),"wave_matches_manifest":sha256(voice)==voice_manifest.get("voice_sha256"),"segment_timing_and_text_match":len(segments)==len(captions) and all(abs(a["start"]-b["start"])<0.02 and abs(a["end"]-b["end"])<0.02 and re.sub(r"\s","",a["text"])==re.sub(r"\s","",b["text"]) for a,b in zip(captions,segments))}
        if not voice_alignment["wave_matches_manifest"] or not voice_alignment["segment_timing_and_text_match"]:
            raise ValueError("Narration waveform or scheduled segments differ from subtitle timing/text")
    sample_times=sorted(set([0.5,25.0,65.0,75.0,115.0,duration/2,150.0,169.0,min(190.0,duration-1),duration-1]))
    raw_samples=[gray_sample(raw,trim+t) for t in (0.5,duration/2,duration-1)]
    if len({x["sha256"] for x in raw_samples})<2:
        raise ValueError("Raw recording QA samples are identical; inspect for static placeholder footage")
    partial=output.with_name(output.stem+".partial.mp4")
    # CWD and all filter filenames are ASCII-relative: avoid Windows drive-colon escaping.
    caption_file=(qa/'subtitles.ass').relative_to(output.parent).as_posix()
    video_filter=f"scale={args.width}:{args.height}:force_original_aspect_ratio=decrease,pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2,setsar=1,subtitles=filename={caption_file}"
    command=[FFMPEG,"-hide_banner","-y","-ss",f"{trim:.6f}","-i",raw,"-i",voice,"-t",f"{duration:.6f}","-map","0:v:0","-map","1:a:0","-vf",video_filter,"-af",f"apad,atrim=duration={duration:.6f},asetpts=PTS-STARTPTS","-r","30","-fps_mode","cfr","-c:v","libx264","-preset","medium","-crf","20","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-ar","48000","-ac","2","-movflags","+faststart","-metadata","title=TaintLab actual local model demonstration",partial]
    print("Encoding the approved actual browser recording, local voice and timed captions...",flush=True)
    run(command,cwd=output.parent,log=qa/"encode.log")
    print("Encoding complete; checking streams, frames, audio and full-video black intervals...",flush=True)
    encoded=probe(partial)
    v=next(s for s in encoded["streams"] if s["codec_type"]=="video")
    a=next((s for s in encoded["streams"] if s["codec_type"]=="audio"),None)
    actual_duration=float(encoded["format"]["duration"])
    checks={"duration_180_to_300":180<=actual_duration<=300.1,"duration_matches_plan":abs(actual_duration-duration)<=0.15,"video_h264":v["codec_name"]=="h264","pixel_format_yuv420p":v["pix_fmt"]=="yuv420p","resolution":(v["width"],v["height"])==(args.width,args.height),"audio_aac":a is not None and a["codec_name"]=="aac","audio_duration_matches_plan":a is not None and abs(float(a.get("duration",actual_duration))-duration)<=0.15}
    decoded_samples=[]
    for t in sample_times:
        frame=qa/f"frame_{round(t*1000):06d}.png"
        run([FFMPEG,"-v","error","-y","-ss",f"{t:.3f}","-i",partial,"-frames:v","1",frame])
        sample=gray_sample(partial,t);sample["image"]=str(frame.relative_to(output.parent)).replace("\\","/")
        decoded_samples.append(sample)
    checks["sample_frames_not_black"]=all(x["mean_luma"]>2 and x["luma_variance"]>0.1 for x in decoded_samples)
    audio_check=subprocess.run([str(FFMPEG),"-hide_banner","-i",str(partial),"-vn","-af","volumedetect","-f","null","-"],capture_output=True)
    audio_log=audio_check.stderr.decode("utf-8",errors="replace")
    (qa/"audio_validation.log").write_text(audio_log,encoding="utf-8")
    match=re.search(r"max_volume:\s+(-?[\d.]+) dB",audio_log)
    max_volume=float(match.group(1)) if match else None
    checks["audio_not_silent"]=audio_check.returncode==0 and max_volume is not None and max_volume>-45
    black_check=subprocess.run([str(FFMPEG),"-hide_banner","-i",str(partial),"-an","-vf","blackdetect=d=1:pix_th=0.10:pic_th=0.98","-f","null","-"],capture_output=True)
    black_log=black_check.stderr.decode("utf-8",errors="replace")
    (qa/"black_detection.log").write_text(black_log,encoding="utf-8")
    black_intervals=re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)",black_log)
    checks["no_black_interval_over_one_second"]=black_check.returncode==0 and not black_intervals
    valid=all(checks.values())
    report={"created_at_utc":datetime.now(timezone.utc).isoformat(),"valid":valid,"checks":checks,"recording_timing":timing,"encoder_version":run([FFMPEG,"-version"]).splitlines()[0],"requested_duration":duration,"actual_duration":actual_duration,"trim_start":trim,"source_duration":source_duration,"source_file":str(raw),"source_sha256":sha256(raw),"voice_file":str(voice),"voice_sha256":sha256(voice),"voice_caption_alignment":voice_alignment,"srt_sha256":sha256(subs),"captions":captions,"caption_font":"Microsoft YaHei","caption_renderer":"libass with explicit ASS PlayRes matching output dimensions","probe":encoded,"raw_frame_samples":raw_samples,"frame_samples":decoded_samples,"audio_max_volume_db":max_volume,"black_intervals":black_intervals,"output":str(output),"video_sha256":sha256(partial),"limitations":"Automated checks establish media properties and sampled frame diversity; human inspection of actual UI, text accuracy, and spoken pronunciation is still required. No artificial video extension or playback-speed adjustment is performed."}
    report['project_version']=args.project_version
    (output.parent/"video_validation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    if not valid:
        raise RuntimeError("Encoded video failed QA; inspect video_validation.json and qa logs. Final file was not replaced.")
    partial.replace(output)
    print(json.dumps({"video":str(output),"duration":actual_duration,"valid":valid,"checks":checks,"qa_frames":[x["image"] for x in decoded_samples]},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
