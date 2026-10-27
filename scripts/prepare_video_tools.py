"""Prepare pinned Windows FFmpeg binaries from the distributor linked by ffmpeg.org."""
import argparse
import json
from pathlib import Path
import subprocess

from model_prepare import ROOT, download, sha256

URL = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.7z"
SHA256 = "4705843ccaaf54257c16ad90f3e952ece33c17df964ecf7bfdbb0f49c7171077"
SIZE = 35430500


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    archive = ROOT / "vendor/downloads/ffmpeg-9.0.2-essentials_build.7z"
    result = download(URL, archive, SHA256, SIZE, offline=args.offline)
    destination = (ROOT / "vendor/ffmpeg").resolve()
    destination.mkdir(parents=True, exist_ok=True)
    names = subprocess.check_output(["tar", "-tf", str(archive)], text=True, encoding="utf-8").splitlines()
    for name in names:
        if not (destination / name).resolve().is_relative_to(destination):
            raise ValueError("FFmpeg archive path escapes extraction directory")
    subprocess.run(["tar", "-xf", str(archive), "-C", str(destination)], check=True)
    bin_dir = destination / "ffmpeg-9.0.2-essentials_build/bin"
    output = {"version":"9.0.2-essentials_build", "distributor":"Gyan Doshi", "source":URL, "archive":result, "binaries":{}}
    for name in ("ffmpeg", "ffprobe", "ffplay"):
        binary = bin_dir / f"{name}.exe"
        version = subprocess.check_output([str(binary), "-version"], text=True, encoding="utf-8", errors="replace")
        output["binaries"][name] = {"path":str(binary.relative_to(ROOT)),"sha256":sha256(binary),"version":version.splitlines()[0]}
    (ROOT / "results/environment/video_tools.json").write_text(json.dumps(output,indent=2),encoding="utf-8")
    print(json.dumps(output,indent=2))


if __name__ == "__main__":
    main()
