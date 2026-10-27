"""Join actual UI recordings at documented cuts; no synthetic UI frames or state edits."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / "vendor/ffmpeg/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-timing", type=Path, default=ROOT / "demo/recording_timing_second_take.json")
    args = parser.parse_args()
    base = json.loads(args.base_timing.read_text(encoding="utf-8-sig"))
    patch = json.loads((ROOT / "demo/patch_recording_metadata.json").read_text(encoding="utf-8-sig"))
    clips = patch["clips"]
    assert len(clips) == 2 and [float(c["duration"]) for c in clips] == [13.0, 14.0]
    paths = [ROOT / base["source_video"]] + [ROOT / c["source_video"] for c in clips]
    for clip, path in zip(clips, paths[1:]):
        assert sha(path) == clip["source_sha256"], "Patch raw bytes differ from recorded provenance"
    # Preserve the previous review artifacts and never confuse them with the edited final video.
    for name in ("video_validation.json", "playback_validation.json", "final_recording_metadata.json"):
        previous = ROOT / "demo" / name
        backup = ROOT / "demo" / (previous.stem + "_before_patch.json")
        if previous.exists() and not backup.exists():
            shutil.copy2(previous, backup)
    previous = ROOT / "demo/demo.mp4"
    backup = ROOT / "demo/raw/second_take_before_patch.mp4"
    if previous.exists() and not backup.exists():
        shutil.copy2(previous, backup)
    output = ROOT / "demo/raw/composed_actual_recording.mkv"
    command = [str(FFMPEG), "-hide_banner", "-y"]
    for path, trim in zip(paths, [base["trim_start"], *[c["trim_start"] for c in clips]]):
        command.extend(["-ss", str(trim), "-i", str(path)])
    normalize = "setpts=PTS-STARTPTS,fps=30,scale=1600:900,setsar=1,format=yuv420p"
    graph = (f"[0:v]split=2[original_start][original_end];"
             f"[original_start]trim=duration=55,{normalize}[a];"
             f"[1:v]trim=duration=13,{normalize}[b];"
             f"[2:v]trim=duration=14,{normalize}[c];"
             f"[original_end]trim=start=82:end=240,{normalize}[d];"
             "[a][b][c][d]concat=n=4:v=1:a=0[out]")
    command.extend(["-filter_complex", graph, "-map", "[out]", "-an", "-c:v", "libx264",
                    "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p", str(output)])
    result = subprocess.run(command, capture_output=True)
    (ROOT / "demo/qa/compose.log").write_bytes(result.stderr)
    if result.returncode:
        raise SystemExit(result.stderr.decode("utf-8", errors="replace")[-2000:])
    timing = {"trim_start": 0, "duration": 240, "source_video": str(output.relative_to(ROOT)),
              "viewport": {"width": 1600, "height": 900},
              "backend": "actual_streamlit_browser_recording_with_documented_cuts",
              "overlays": [
                  {"start": 55, "end": 68, "text": "外部网页正文 · 实际界面补录（加载已剪辑）"},
                  {"start": 68, "end": 82, "text": "正式冻结版 真实运行记录回放（加载已剪辑）"},
                  {"start": 82, "end": 148, "text": "正式冻结版 真实运行记录回放"},
                  {"start": 148, "end": 176, "text": "旧开发版 development_v3 真实记录回放"}],
              "edits": [
                  {"output_start": 0, "duration": 55, "source_video": base["source_video"], "trim_start": base["trim_start"], "source_sha256": sha(paths[0])},
                  {"output_start": 55, **clips[0]},
                  {"output_start": 68, **clips[1]},
                  {"output_start": 82, "duration": 158, "source_video": base["source_video"], "trim_start": base["trim_start"] + 82, "source_sha256": sha(paths[0])}],
              "edit_note": "Only actual UI footage is joined. Waiting before the two supplemental recordings is removed and labelled. No playback acceleration, artificial extension, or experiment-state modification."}
    (ROOT / "demo/recording_timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "demo/composition_manifest.json").write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat(), "source_sha256": sha(output), **timing}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
