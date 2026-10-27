"""Download pinned official artifacts, verify SHA256, safely unpack. Python stdlib only."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def download(url: str, path: Path, expected: str, size: int, offline: bool = False) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and sha256(path) == expected:
        print(f"verified {path.name}", flush=True)
        return {"path": str(path.relative_to(ROOT)), "sha256": expected, "bytes": path.stat().st_size}
    if offline:
        raise RuntimeError(f"Missing or invalid offline artifact: {path.name}")
    # Bounded HTTP range parts survive interrupted downloads and short reads.
    # Every part is length-checked; the reassembled file is authenticated by its pinned SHA256.
    partial = path.with_name(path.name + ".part")
    parts_dir = path.with_name(path.name + ".chunks")
    parts_dir.mkdir(exist_ok=True)
    block_size = 2 * 1024 * 1024
    count = (size + block_size - 1) // block_size
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Range": "bytes=0-0"}), timeout=60) as response:
        resolved_url = response.geturl()
    def get_part(index):
        start = index * block_size
        end = min(size, start + block_size) - 1
        part = parts_dir / f"{index:05d}.part"
        expected_length = end - start + 1
        if part.exists() and part.stat().st_size == expected_length:
            return expected_length
        for attempt in range(5):
            try:
                request = urllib.request.Request(resolved_url, headers={"Range": f"bytes={start}-{end}", "User-Agent": "TaintLab/1.0"})
                with urllib.request.urlopen(request, timeout=45) as response:
                    if response.status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {start}-"):
                        raise ValueError("Server did not honor requested byte range")
                    data = response.read(expected_length + 1)
                if len(data) != expected_length:
                    raise ValueError("Short ranged response")
                part.write_bytes(data)
                return len(data)
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(1 + attempt)
    downloaded = 0
    last_report = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        for future in concurrent.futures.as_completed([pool.submit(get_part, i) for i in range(count)]):
            downloaded += future.result()
            if time.monotonic() - last_report > 20:
                print(f"downloading {path.name}: {downloaded / 1048576:.1f}/{size / 1048576:.1f} MiB", flush=True)
                last_report = time.monotonic()
    with partial.open("wb") as output:
        for index in range(count):
            output.write((parts_dir / f"{index:05d}.part").read_bytes())
    actual = sha256(partial)
    if actual != expected:
        raise RuntimeError(f"SHA256 mismatch {path.name}: {actual}")
    partial.replace(path)
    # Delete only explicitly named verified chunk files beneath this target.
    for index in range(count):
        (parts_dir / f"{index:05d}.part").unlink()
    parts_dir.rmdir()
    print(f"downloaded and verified {path.name}: {size} bytes", flush=True)
    return {"path": str(path.relative_to(ROOT)), "sha256": actual, "bytes": size}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Verify cached artifacts without any network request")
    args = parser.parse_args()
    lock = json.loads((ROOT / "configs/model.lock.json").read_text(encoding="utf-8"))
    jobs = [(lock["model_url"], ROOT / lock["model_file"], lock["model_sha256"], lock["model_size_bytes"])]
    jobs += [(a["url"], ROOT / "vendor/downloads" / a["name"], a["sha256"], a["size_bytes"]) for a in lock["archives"]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda j: download(*j, offline=args.offline), jobs))
    destination = (ROOT / "vendor/llama.cpp").resolve()
    destination.mkdir(parents=True, exist_ok=True)
    runtime_manifest = destination / "verified_runtime.json"
    if runtime_manifest.exists():
        previous = json.loads(runtime_manifest.read_text(encoding="utf-8"))
        runtime_valid = all((destination / name).is_file() and sha256(destination / name) == digest for name, digest in previous.items())
    else:
        runtime_valid = False
    if not runtime_valid:
        if args.offline and runtime_manifest.exists():
            raise RuntimeError("Extracted runtime validation failed; rerun preparation without --offline to repair")
        runtime_hashes = {}
        for archive in lock["archives"]:
            with zipfile.ZipFile(ROOT / "vendor/downloads" / archive["name"]) as zf:
                for item in zf.infolist():
                    target = (destination / item.filename).resolve()
                    if not target.is_relative_to(destination):
                        raise ValueError("Archive path escaped extraction directory")
                zf.extractall(destination)
                for item in zf.infolist():
                    if not item.is_dir():
                        runtime_hashes[item.filename] = sha256(destination / item.filename)
        runtime_manifest.write_text(json.dumps(runtime_hashes, indent=2), encoding="utf-8")
    evidence = ROOT / "results/environment"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "artifact_verification.json").write_text(json.dumps({"verified_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "offline": args.offline, "artifacts": results}, indent=2), encoding="utf-8")
    print("Model and runtime ready. Start with scripts/start_model.ps1", flush=True)


if __name__ == "__main__":
    main()
