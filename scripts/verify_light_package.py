"""Independently extract and verify a light delivery without starting services.

Example: python scripts/verify_light_package.py --install offline --run-packaging-tests
The final JSON is outside the ZIP by default, avoiding recursive package hashes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = "taintlab_project"
FORMAL_COUNTS = {"main": 972, "ablation": 324, "v2/baseline": 1296, "v2/external": 1080}
NETWORK_GUARD = "import socket\ndef deny(*a,**k): raise RuntimeError('Network is disabled in package verification')\nsocket.socket.connect=deny\nsocket.socket.connect_ex=deny\nsocket.create_connection=deny\n"


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def safe_member(name: str) -> PurePosixPath:
    if "\\" in name or ":" in name or any(ord(char) < 32 for char in name):
        raise ValueError("Unsafe archive member name: " + repr(name))
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != PACKAGE_ROOT:
        raise ValueError("Archive member escapes the package root: " + repr(name))
    return path


def enforce_light_privacy(path: PurePosixPath) -> None:
    lower = [p.casefold() for p in path.parts]
    name = lower[-1]
    if any(p in {"web_private", "node_modules", ".git", "__pycache__", ".validation-build"} or p.startswith(".venv") for p in lower):
        raise ValueError("Private/runtime dependency found in light archive: " + str(path))
    if name in {".env", "secrets.toml", ".validation-target.txt"} or name.startswith(".env.") or name.endswith((".sqlite", ".sqlite3", ".db", ".sqlite-wal", ".sqlite-shm", ".pid", ".lock", ".lck", ".tsbuildinfo")):
        raise ValueError("Private/runtime state found in light archive: " + str(path))


def extract_and_verify(archive_path: Path, destination: Path) -> tuple[Path, dict, list[dict]]:
    if destination.exists():
        raise ValueError("Destination must be a new independent directory: " + str(destination))
    with zipfile.ZipFile(archive_path) as archive:
        seen = set()
        for entry in archive.infolist():
            member = safe_member(entry.filename)
            enforce_light_privacy(member)
            key = entry.filename.casefold()
            if key in seen or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                raise ValueError("Duplicate, linked or encrypted ZIP entry: " + entry.filename)
            seen.add(key)
        manifest = json.loads(archive.read(f"{PACKAGE_ROOT}/DELIVERY_MANIFEST.json"))
        if manifest.get("profile") != "light":
            raise ValueError("Expected the light package profile")
        files = manifest.get("files", {})
        if not isinstance(files, dict) or not files:
            raise ValueError("Missing per-file manifest")
        for name, meta in files.items():
            safe_member(f"{PACKAGE_ROOT}/{name}")
            if not re.fullmatch(r"[0-9a-f]{64}", meta.get("sha256", "")) or not isinstance(meta.get("bytes"), int) or meta["bytes"] < 0:
                raise ValueError("Invalid manifest entry: " + name)
        expected = {f"{PACKAGE_ROOT}/{name}" for name in files} | {f"{PACKAGE_ROOT}/DELIVERY_MANIFEST.json", f"{PACKAGE_ROOT}/PACKAGE_SHA256SUMS.txt"}
        actual = {entry.filename for entry in archive.infolist() if not entry.is_dir()}
        if actual != expected or archive.testzip() is not None:
            raise ValueError("ZIP entry list/CRC does not match the manifest")
        sums = {}
        for line in archive.read(f"{PACKAGE_ROOT}/PACKAGE_SHA256SUMS.txt").decode("utf-8").splitlines():
            digest, name = line.split("  ", 1)
            if name in sums:
                raise ValueError("Duplicate checksum entry")
            sums[name] = digest
        if sums != {name: meta["sha256"] for name, meta in files.items()}:
            raise ValueError("Per-file checksum list disagrees with manifest")
        destination.mkdir(parents=True)
        archive.extractall(destination)
    extracted = destination / PACKAGE_ROOT
    verification = []
    for name, meta in files.items():
        path = extracted / name
        actual_hash = sha(path)
        if actual_hash != meta["sha256"] or path.stat().st_size != meta["bytes"]:
            raise ValueError("Extracted file hash/size mismatch: " + name)
        verification.append({"path": name, "sha256": actual_hash, "bytes": path.stat().st_size, "passed": True})
    return extracted, manifest, verification


def formal_evidence(root: Path) -> dict:
    counts = {}
    for group, expected in FORMAL_COUNTS.items():
        directory = root / "results" / group
        paths = sorted((directory / "records").glob("*.json"))
        identifiers = {path.stem for path in paths}
        rows = [json.loads(line) for line in (directory / "metrics.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        manifest = read_json(directory / "experiment_manifest.json")
        if len(paths) != expected or len(rows) != expected or manifest["planned_runs"] != expected or {row["run_id"] for row in rows} != identifiers:
            raise ValueError("Formal run/index count mismatch: " + group)
        for path in paths:
            record = read_json(path)
            if record["run_id"] != path.stem or record.get("backend_type") != "local_llama_cpp":
                raise ValueError("Formal record identity/backend mismatch: " + path.name)
        for name in ("summary.json", "metrics.csv", "paired_scenarios.json"):
            if not (directory / name).is_file():
                raise ValueError("Missing formal artifact: " + name)
        if read_json(directory / "summary.json").get("total_runs") != expected:
            raise ValueError("Formal summary count mismatch: " + group)
        counts[group] = len(paths)
    return counts


def verify_current_source(root: Path, manifest: dict) -> dict:
    source = manifest.get("current_source", {})
    entries = source.get("files", {})
    if not entries:
        raise ValueError("Missing current delivered source manifest")
    for name, meta in entries.items():
        if name not in manifest["files"] or meta != manifest["files"][name] or sha(root / name) != meta["sha256"]:
            raise ValueError("Current source manifest differs from delivered bytes: " + name)
    expected = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if source.get("fingerprint") != expected:
        raise ValueError("Current source fingerprint mismatch")
    return {"files": len(entries), "fingerprint": expected, "passed": True}


def verify_frontend(root: Path) -> dict:
    """Read bytes and references independently of the builder's saved verdict."""
    frontend = root / "frontend"
    manifest = read_json(frontend / "build_manifest.json")
    if manifest.get("build_returncode") != 0:
        raise ValueError("Frontend compile receipt is missing or failed")
    source_paths = [frontend / p for p in ("package.json", "package-lock.json", "index.html", "tsconfig.json", "vite.config.ts") if (frontend / p).is_file()]
    source_paths += [p for folder in (frontend / "src", frontend / "public") if folder.exists() for p in folder.rglob("*") if p.is_file()]
    artifact_paths = [p for p in (frontend / "dist").rglob("*") if p.is_file()]
    for paths, key in ((source_paths, "source_files"), (artifact_paths, "artifact_files")):
        actual = {p.relative_to(root).as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size} for p in paths}
        if not actual or actual != manifest.get(key):
            raise ValueError("Frontend source/artifact hash mismatch: " + key)
    fingerprint = hashlib.sha256(json.dumps(manifest["source_files"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if fingerprint != manifest.get("source_fingerprint"):
        raise ValueError("Frontend source fingerprint mismatch")
    clean = read_json(frontend / "qa/clean_install_validation.json")
    clean_tests = read_json(frontend / "qa/clean_install_tests.json")
    if clean.get("install_exit_code") != 0 or not clean.get("all_assets_identical") or clean.get("package_lock_sha256") != sha(frontend / "package-lock.json") or not clean_tests.get("success") or clean_tests.get("numFailedTests") != 0 or clean_tests.get("numPassedTests") != clean.get("tests_passed"):
        raise ValueError("Frontend clean installation/test evidence mismatch")
    dist = (frontend / "dist").resolve()
    if not (dist / "index.html").is_file():
        raise ValueError("Missing frontend entry")
    from urllib.parse import urlsplit, unquote
    references = []
    for p in artifact_paths:
        if p.suffix.lower() not in {".html", ".css", ".js", ".mjs"}:
            continue
        text = p.read_text(encoding="utf-8")
        if p.suffix == ".html":
            values = re.findall(r"<(?:script|img|source|video|audio|iframe|link)\b[^>]*\b(?:src|href|poster)=[\"']([^\"']+)", text, flags=re.I)
        elif p.suffix == ".css":
            values = re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", text) + re.findall(r"@import\s+['\"]([^'\"]+)", text)
        else:
            values = re.findall(r"\b(?:from\s*|import\s*(?:\(\s*)?)[\"']([^\"']+)[\"']", text)
            values += re.findall(r"new\s+URL\(\s*['\"]([^'\"]+)['\"]\s*,\s*import\.meta\.url", text)
            values = [v for v in values if v.startswith((".", "/"))]
        for value in values:
            url = urlsplit(value)
            if not value or value.startswith("#") or url.scheme in {"data", "blob"}:
                continue
            if url.scheme or url.netloc:
                raise ValueError("Remote frontend auto-loaded dependency")
            asset_path = unquote(url.path)
            target = (dist / asset_path.lstrip("/")) if asset_path.startswith("/") else p.parent / asset_path
            target = target.resolve()
            if not target.is_relative_to(dist) or not target.is_file():
                raise ValueError("Missing/escaping frontend static reference: " + value)
            references.append(target.relative_to(root).as_posix())
    return {"source_files": len(source_paths), "artifacts": len(artifact_paths), "references_checked": len(references), "source_fingerprint": fingerprint, "clean_install_tests_passed": clean["tests_passed"], "passed": True}


def verify_frozen_data(root: Path) -> dict:
    counts = {}
    for prefix in (Path("data"), Path("data/v2")):
        frozen = read_json(root / prefix / "frozen_manifest.json")
        if not frozen.get("frozen"):
            raise ValueError("Dataset is not frozen")
        for name, expected in frozen["files"].items():
            path = (root / prefix / name).resolve()
            if not path.is_relative_to((root / prefix).resolve()) or not path.is_file() or sha(path) != expected:
                raise ValueError("Frozen source/data/license mismatch: " + str(prefix / name))
        counts[prefix.as_posix()] = len(frozen["files"])
    return {"checked_files": counts, "passed": True}


def verify_demo_evidence(root: Path) -> dict:
    document = read_json(root / "demo/selected_evidence.json")
    if not isinstance(document, dict):
        raise ValueError("Invalid selected demo evidence")
    modern = "records" in document
    pending = [document["records"]] if modern else [v for v in document.values() if isinstance(v, dict) and "path" in v]
    if modern and (not isinstance(document["records"], list) or not document["records"]):
        raise ValueError("Selected demo records must be a non-empty array")
    checked = []
    while pending:
        item = pending.pop(0)
        if isinstance(item, list):
            if not item:
                raise ValueError("Empty selected demo record group")
            pending[0:0] = item
            continue
        if not isinstance(item, dict):
            raise ValueError("Invalid selected demo record entry")
        if "path" not in item:
            groups = [v for v in item.values() if isinstance(v, (list, dict))]
            if not groups:
                raise ValueError("Selected demo record has no path")
            pending[0:0] = groups
            continue
        name = item["path"]
        if not isinstance(name, str) or not name:
            raise ValueError("Invalid selected demo record path")
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Selected demo record is missing or escaping")
        relative = path.relative_to(root).as_posix()
        parts = PurePosixPath(relative).parts
        enforce_light_privacy(PurePosixPath(PACKAGE_ROOT) / relative)
        if parts[0] != "results" or path.suffix.lower() != ".json" or not ("records" in parts or parts[:3] in {("results", "v2", "acceptance"), ("results", "v2", "demo")}):
            raise ValueError("Selected demo path is outside approved evidence roles")
        declared = item.get("sha256")
        if (modern or declared is not None) and (not isinstance(declared, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", declared)):
            raise ValueError("Selected demo record is missing a SHA256")
        actual = sha(path)
        if declared is not None and actual != declared.lower():
            raise ValueError("Selected demo record SHA256 mismatch")
        checked.append({"path": relative, "sha256": actual})
    return {"checked_records": len(checked), "records": checked, "passed": True}


def verify_current_reviews(root: Path) -> dict:
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    visual = read_json(root / "demo/v2/visual_review.json")
    passed = visual.get("all_passed") is True or visual.get("passed") is True
    if visual.get("project_version") != version or not passed or visual.get("all_passed") is False or visual.get("passed") is False or visual.get("video_sha256") != sha(root / "demo/demo.mp4"):
        raise ValueError("Current video visual review is failed, stale or has a different version")
    mirrors = ["document_validation.json", "structure_validation.json", "visual_review_page_hashes.json", "visual_review.md"]
    for name in mirrors:
        if sha(root / "docs/qa" / name) != sha(root / "docs/v2/qa" / name):
            raise ValueError("Current document QA mirrors disagree")
    browser = read_json(root / "results/v2/browser/ui_acceptance.json")
    if browser.get("version") != version or browser.get("all_targeted_checks_passed_latest_evidence") is not True:
        raise ValueError("Current browser acceptance conclusion/version invalid")
    references = {}
    pending = [browser]
    reference_keys = {"path", "report", "evidence_report", "follow_up", "review_record", "recording_timing_review"}
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, (dict, list)):
                    pending.append(child)
                elif key in reference_keys and isinstance(child, str):
                    name = child.replace("\\", "/")
                    if not name.startswith("results/v2/browser/") or Path(name).suffix not in {".json", ".md"}:
                        continue
                    target = (root / name).resolve()
                    if not target.is_relative_to((root / "results/v2/browser").resolve()) or not target.is_file():
                        raise ValueError("Browser acceptance has a missing or escaping report reference")
                    enforce_light_privacy(PurePosixPath(PACKAGE_ROOT) / name)
                    expected = value.get("sha256") if key == "path" else value.get("review_sha256") if key == "review_record" else None
                    actual = sha(target)
                    if expected is not None and expected != actual:
                        raise ValueError("Browser acceptance referenced report hash mismatch")
                    references[name] = actual
    return {"passed": True, "video_visual_review": "demo/v2/visual_review.json", "video_sha256": visual["video_sha256"], "document_qa_mirrors": mirrors, "browser_reports": references, "scope": "Saved current review and report references; excluded QA PNG/raw recordings are not claimed to be redistributed."}


def verify_user_manual(root: Path) -> dict:
    expected = read_json(root / "docs/publication/manual_qa/manual_validation.json")
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if expected.get("project_version") != version or expected.get("all_passed") is not True or not expected.get("visual_review") or expected.get("visual_review") in {"pending", "required_after_latest_render"}:
        raise ValueError("User manual final review is missing or incomplete")
    checked = {}
    for suffix, field in (("md", "source_markdown_sha256"), ("docx", "docx_sha256"), ("pdf", "pdf_sha256")):
        name = "docs/USER_MANUAL." + suffix
        if not (root / name).is_file() or sha(root / name) != expected.get(field):
            raise ValueError("User manual artifact hash mismatch: " + name)
        checked[name] = expected[field]
    for name, digest in expected.get("assets", {}).items():
        target = (root / name).resolve()
        if not target.is_relative_to((root / "docs/assets/user-manual").resolve()) or not target.is_file() or sha(target) != digest:
            raise ValueError("User manual asset hash mismatch or path escape")
    return {"passed": True, "artifacts": checked, "pages": expected["pages"], "assets_checked": len(expected.get("assets", {}))}


def portable_paths(root: Path, original_root: Path) -> dict:
    readme = (root / "README.md").read_text(encoding="utf-8-sig")
    references = sorted(set(re.findall(r"(?:scripts|src|configs|data|docs|demo)[/\\][A-Za-z0-9_./\\\-\u4e00-\u9fff]+", readme)))
    generated_outputs = {"data/reproduced"}
    missing = [value for value in references if value.replace("\\", "/").rstrip(".") not in generated_outputs and not (root / value.replace("\\", "/").rstrip(".")).exists()]
    if missing:
        raise ValueError("README references missing local paths: " + ", ".join(missing))
    sources = ["启动项目.cmd", "关闭项目.cmd", "scripts/model_prepare.py", "scripts/project_lifecycle.py", "scripts/launch_model.py", "scripts/install.ps1", "configs/model.json", "configs/model.lock.json", "configs/launcher.json"]
    system_fallbacks = []
    for name in sources:
        text = (root / name).read_text(encoding="utf-8-sig")
        normalized = text.replace("\\", "/").casefold()
        # The exact Windows SystemRoot default is an OS lookup, not a pinned
        # project location. No other absolute drive literal is exempted.
        fallback = 'os.environ.get("SystemRoot", r"C:\\Windows")'
        scan = text
        if name == "scripts/project_lifecycle.py" and fallback in text:
            scan = text.replace(fallback, 'os.environ.get("SystemRoot")')
            system_fallbacks.append({"file": name, "environment": "SystemRoot", "default": "C:/Windows"})
        if original_root.as_posix().casefold() in normalized or re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[/\\]", scan):
            raise ValueError("Runtime/preparation entry contains an absolute original-machine path: " + name)
        if name.endswith(".cmd") and ("%~dp0" not in text or name not in readme):
            raise ValueError("CMD entry is not rooted at its extracted location or absent from README: " + name)
    lock = read_json(root / "configs/model.lock.json")
    model_path = Path(lock["model_file"])
    if model_path.is_absolute() or ".." in model_path.parts or not (root / model_path).resolve().is_relative_to(root.resolve()):
        raise ValueError("Model destination is not a portable package-relative path")
    return {"readme_local_references": references, "expected_after_reproduction": sorted(value for value in references if value.replace("\\", "/").rstrip(".") in generated_outputs), "checked_runtime_files": sources, "system_directory_fallbacks": system_fallbacks, "model_file": model_path.as_posix(), "original_root_references_in_runtime": [], "historical_evidence_paths": "Old environment/validation paths are provenance only and are not rewritten or treated as executable dependencies."}


def command(args: list[str], cwd: Path, log: Path, timeout=240) -> str:
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", UV_OFFLINE="1", UV_NO_PROGRESS="1")
    result = subprocess.run(args, cwd=cwd, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(args, ensure_ascii=False) + "\n" + result.stdout + result.stderr + f"\nEXIT {result.returncode}\n")
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}: " + args[0])
    return result.stdout


def fresh_install(root: Path, log: Path, run_tests: bool) -> dict:
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("Offline installation requires uv and its existing package cache")
    environment = root / ".venv"
    if environment.exists():
        raise ValueError("Fresh verification environment already exists")
    base_python = getattr(sys, "_base_executable", sys.executable)
    command([uv, "venv", "--offline", "--python", base_python, str(environment)], root, log)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    command([uv, "pip", "install", "--offline", "--python", str(python), "-r", "requirements.lock.txt"], root, log)
    command([uv, "pip", "install", "--offline", "--python", str(python), "--no-deps", "--no-build-isolation", "-e", "."], root, log)
    command([uv, "pip", "check", "--python", str(python)], root, log)
    # All application probes deny socket connection attempts, including loopback.
    probe = NETWORK_GUARD + "import importlib,json,pathlib,sys,taintlab\nr=pathlib.Path.cwd().resolve()\nassert pathlib.Path(taintlab.__file__).resolve().is_relative_to(r)\nsys.path.insert(0,str(r/'scripts'))\nmodules={n:str(importlib.import_module(n).ROOT) for n in ['model_prepare','launch_model','project_lifecycle']}\nassert all(pathlib.Path(p).resolve()==r for p in modules.values())\nprint(json.dumps({'package':taintlab.__file__,'module_roots':modules}))\n"
    roots = json.loads(command([str(python), "-c", probe], root, log))
    command([str(python), "-c", NETWORK_GUARD + "import runpy,sys\nsys.argv=['taintlab','--help']\nrunpy.run_module('taintlab.cli',run_name='__main__')"], root, log)
    command([str(python), "scripts/model_prepare.py", "--help"], root, log)
    tests = None
    if run_tests:
        targets = [name for name in ("tests/test_packaging.py", "tests/test_package_verification.py") if (root / name).exists()]
        output = command([str(python), "-c", NETWORK_GUARD + "import pytest,sys\nsys.exit(pytest.main(" + repr(targets + ["-q", "--junitxml=package_verification_pytest.xml"]) + "))"], root, log)
        suite = ET.parse(root / "package_verification_pytest.xml").getroot().find("testsuite")
        tests = {key: int(suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")}
        tests["targets"] = targets
    return {"mode": "uv_offline_cache_new_environment", "fresh_environment": str(environment), "copied_old_venv": False, "python": str(python), "base_python": base_python, "dependency_check_passed": True, "imports": roots, "cli_help_passed": True, "model_preparation_help_passed": True, "application_probe_socket_connections": "all denied", "tests": tests}


DOCUMENT_PROBE = """
import json,sys,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
from pypdf import PdfReader
r=Path(sys.argv[1]); doc=r/'dist/project_report.docx'; pdf=r/'dist/project_report.pdf'
with zipfile.ZipFile(doc) as z:
 assert z.testzip() is None
 t=ET.fromstring(z.read('word/document.xml'))
 text=''.join(t.itertext()); assert any('\\u4e00'<=c<='\\u9fff' for c in text)
reader=PdfReader(pdf); assert len(reader.pages)>0
indices=sorted(set([0,len(reader.pages)//2,len(reader.pages)-1]))
samples=[{'page':i+1,'characters':len(reader.pages[i].extract_text() or '')} for i in indices]
assert all(s['characters']>30 for s in samples)
with zipfile.ZipFile(r/'docs/USER_MANUAL.docx') as z:
 assert z.testzip() is None
 mt=ET.fromstring(z.read('word/document.xml'))
 assert any('\\u4e00'<=c<='\\u9fff' for c in ''.join(mt.itertext()))
manual=PdfReader(r/'docs/USER_MANUAL.pdf'); assert len(manual.pages)>0
mi=sorted(set([0,len(manual.pages)//2,len(manual.pages)-1]))
ms=[{'page':i+1,'characters':len(manual.pages[i].extract_text() or '')} for i in mi]
assert all(s['characters']>30 for s in ms)
print(json.dumps({'docx':{'zip_crc':True,'document_xml_parsed':True,'chinese_text_present':True},'pdf':{'pages':len(reader.pages),'text_samples':samples},'manual':{'docx_zip_xml_chinese_checked':True,'pages':len(manual.pages),'text_samples':ms},'scope':'Container/XML/PDF text parsing only; no new human page-layout review.'}))
"""


def check_media(root: Path, ffprobe: Path, document_python: Path, log: Path) -> dict:
    video = root / "demo/demo.mp4"
    probe = json.loads(command([str(ffprobe), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)], root, log))
    v = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
    a = next(stream for stream in probe["streams"] if stream["codec_type"] == "audio")
    duration = float(probe["format"]["duration"])
    if not (180 <= duration <= 300) or v["codec_name"] != "h264" or a["codec_name"] != "aac" or v["pix_fmt"] != "yuv420p":
        raise ValueError("Unexpected delivered media properties")
    ffmpeg = ffprobe.with_name("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    command([str(ffmpeg), "-hide_banner", "-v", "error", "-i", str(video), "-f", "null", "-"], root, log)
    documents = json.loads(command([str(document_python), "-c", NETWORK_GUARD + DOCUMENT_PROBE, str(root)], root, log))
    expected = read_json(root / "docs/qa/document_validation.json")
    if documents["pdf"]["pages"] != expected["pages"]:
        raise ValueError("PDF page count differs from the saved document validation")
    if documents["manual"]["pages"] != read_json(root / "docs/publication/manual_qa/manual_validation.json")["pages"]:
        raise ValueError("User manual PDF page count differs from its saved validation")
    return {"video": {"duration": duration, "resolution": [v["width"], v["height"]], "video_codec": v["codec_name"], "audio_codec": a["codec_name"], "full_decode_passed": True}, "documents": documents, "tools": {"ffprobe": str(ffprobe), "document_python": str(document_python)}}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "dist/taintlab_project_light.zip")
    parser.add_argument("--destination", type=Path, help="Must not exist; default is a unique directory under dist/package_light_verify")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/light_package_validation.json")
    parser.add_argument("--install", choices=("none", "offline"), default="none")
    parser.add_argument("--run-packaging-tests", action="store_true")
    parser.add_argument("--skip-media", action="store_true", help="Explicitly skip media checks and record that limitation")
    parser.add_argument("--ffprobe", type=Path, default=ROOT / "vendor/ffmpeg/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe")
    parser.add_argument("--document-python", type=Path, default=Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    archive = args.archive.resolve()
    destination = (args.destination or ROOT / "dist/package_light_verify" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secrets.token_hex(4))).resolve()
    output = args.output.resolve()
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "kind": "independent_light_archive_extraction_verification", "archive": str(archive), "destination": str(destination), "all_passed": False, "services_started_or_stopped": False, "model_downloaded": False, "scope": "Independent extraction, file hashes, saved evidence and portable entries. Optional offline-cache clean installation; no model/UI startup and no global Windows network changes."}
    try:
        if args.run_packaging_tests and args.install != "offline":
            raise ValueError("--run-packaging-tests requires --install offline")
        report["archive_sha256"] = sha(archive)
        report["archive_bytes"] = archive.stat().st_size
        extracted, manifest, verified = extract_and_verify(archive, destination)
        log = destination / "verification_commands.log"
        report["extracted_root"] = str(extracted)
        report["manifest_profile"] = manifest["profile"]
        report["verified_files"] = verified
        report["file_count"] = len(verified)
        report["formal_records"] = formal_evidence(extracted)
        report["current_source"] = verify_current_source(extracted, manifest)
        report["frontend"] = verify_frontend(extracted)
        report["frozen_data"] = verify_frozen_data(extracted)
        report["demo_evidence"] = verify_demo_evidence(extracted)
        report["current_reviews"] = verify_current_reviews(extracted)
        report["user_manual"] = verify_user_manual(extracted)
        report["portable_paths"] = portable_paths(extracted, ROOT)
        report["installation"] = fresh_install(extracted, log, args.run_packaging_tests) if args.install == "offline" else {"mode": "not_requested"}
        report["media"] = {"status": "explicitly_skipped"} if args.skip_media else check_media(extracted, args.ffprobe.resolve(), args.document_python.resolve(), log)
        report["archive_unchanged_during_verification"] = sha(archive) == report["archive_sha256"]
        if not report["archive_unchanged_during_verification"]:
            raise ValueError("Archive changed during verification")
        report["all_passed"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report.get(key) for key in ("all_passed", "archive", "archive_sha256", "destination", "file_count", "formal_records", "error")}, ensure_ascii=False, indent=2))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
