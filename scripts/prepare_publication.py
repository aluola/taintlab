"""Prepare an independently reviewed public snapshot without Git mutations.

The source checkout and its history/evidence remain unchanged. Private diagnostics
are excluded or replaced in the new tree by explicitly labelled public summaries.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=None)
def module(name: str):
    spec = importlib.util.spec_from_file_location("publication_" + name, Path(__file__).with_name(name + ".py"))
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def encoded(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def public_exclusion(name: str) -> str | None:
    p = Path(name)
    if any(part.lower() in {"reference", "references", "reference_source", "upstream_repo", "third_party", "third-party"} for part in p.parts):
        return "third_party_reference_sources_not_redistribution_approved"
    if p.parts[:2] in {("results", "environment"), ("results", "launcher"), ("results", "validation")}:
        return "private_machine_or_historical_environment_diagnostics"
    if p.parts[:3] == ("results", "v2", "launcher") and name != "results/v2/launcher/validation/actual_windows_validation.json":
        return "private_launcher_diagnostics"
    if p.parts[:3] == ("results", "v2", "validation") and name != "results/v2/validation/experiment_integrity.json":
        return "private_validation_output_represented_by_public_summary"
    if p.parts[:3] == ("results", "v2", "acceptance"):
        return "raw_runtime_acceptance_represented_by_public_summary"
    if p.parts[:2] == ("docs", "qa") and p.name in {"renderer_environment.json", "README.md", "prepare_renderer.py", "verify_documents.py"}:
        return "local_document_renderer_environment"
    if p.parts[:2] == ("docs", "history"):
        return "historical_local_delivery_notes"
    return None


def summary_origin(name: str, raw: bytes) -> dict:
    return {"publication_summary": True, "source_evidence_path": name, "original_evidence_sha256": digest(raw), "disclosure": "Explicit public summary of saved local evidence. Machine paths, process identities, browser credentials and uploaded runtime bodies are not redistributed. This is not a newly executed acceptance test."}


def summary_fields(name: str) -> set[str] | None:
    if name.startswith("frontend/qa/"):
        return {"generated_at", "install_exit_code", "installed_packages", "tests_passed", "package_lock_sha256", "all_assets_identical", "assets", "success", "numPassedTests", "numFailedTests", "numPendingTests", "numTotalTests"}
    if name == "results/v2/launcher/validation/actual_windows_validation.json":
        return {"started_at", "finished_at", "kind", "version", "checks", "all_passed", "completed_v2_campaigns"}
    if name.startswith("results/v2/browser/") and name.endswith(".json"):
        return {"generated_at", "started_at", "captured_at", "reviewed_at_utc", "version", "project_version", "checks", "all_passed", "all_targeted_checks_passed_latest_evidence", "unique_check_count", "latest_unique_checks_passed", "counting_note", "browser_reports", "latest_evidence_by_unique_check", "production_assets", "preserved_failures", "narrow_screen", "visual_review", "recording_timing_review", "status", "scope", "limitations", "model_health", "backend_type", "run_id", "selected_event", "visible_nodes", "errors", "blocked_external"}
    if name in {"demo/video_validation.json", "demo/playback_validation.json"}:
        return {"project_version", "created_at_utc", "checked_at", "valid", "all_passed", "checks", "actual_duration", "requested_duration", "video_sha256", "srt_sha256", "encoder_version", "metadata", "samples", "blocked_external_origins"}
    if name == "demo/v2/narration_synthesis.json":
        return {"created_at_utc", "backend_type", "voice", "requested_duration_seconds", "actual_duration_seconds", "sample_rate", "channels", "codec", "atempo_range", "narration_sha256", "voice_sha256", "network_required", "limits"}
    if name.startswith(("docs/qa/", "docs/v2/qa/")) and name.endswith("document_validation.json"):
        return {"project_version", "generated_at", "pages", "toc_pages", "docx_sha256", "pdf_sha256", "source_markdown_sha256", "visual_review", "review_report", "review_sha256"}
    if name.startswith("docs/publication/manual_qa/") and name.endswith(".json"):
        return {"project_version", "generated_at", "checked_at", "reviewed_at_utc", "all_passed", "pages", "total_pages", "reviewed_pages", "docx_sha256", "pdf_sha256", "source_markdown_sha256", "assets", "visual_review", "artifact_hashes", "checks", "method", "scope", "limitations", "findings", "issues"}
    return None


def public_value(value):
    """Summaries retain explicit assertions; omit raw bodies/process/session data."""
    private_keys = {"pid", "parent_pid", "exe", "argv", "headers", "cookies", "cookie", "owners", "owner", "session", "sessions", "session_id", "upload_body", "body", "content", "messages", "state", "initial", "final", "evidence", "staging_directory", "path_on_host"}
    if isinstance(value, dict):
        return {key: public_value(child) for key, child in value.items() if key not in private_keys}
    if isinstance(value, list):
        return [public_value(child) for child in value]
    if isinstance(value, str):
        audit = module("audit_publication")
        if audit.PRIVATE_ENVIRONMENT.search(value.encode("utf-8")) or re.search(r"(?i)(?<![A-Z0-9])[A-Z]:[\\/]|^file://", value):
            return "[local-machine path omitted in public summary]"
    return value


def project_file(name: str, content: bytes) -> tuple[bytes, str]:
    if name == "AGENTS.md":
        text = content.decode("utf-8-sig")
        heading = "# 项目维护与交付约定"
        if heading not in text:
            raise ValueError("AGENTS public projection needs an explicit project-maintenance section")
        projected = text[text.index(heading):]
        if re.search(r"(?i)gmail|CODEX_GMAIL_PER_TURN|[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", projected):
            raise ValueError("Personal notification instructions cannot enter public AGENTS")
        public = projected.encode("utf-8")
        return public, "project_maintenance_instructions_only" if public != content else "unchanged_project_maintenance_instructions"
    fields = summary_fields(name)
    if fields is None:
        return content, "unchanged_source_file"
    original = json.loads(content.decode("utf-8-sig"))
    canonical_name = name.replace("docs/v2/qa/", "docs/qa/", 1) if name.endswith("document_validation.json") else name
    result = summary_origin(canonical_name, content)
    result.update({key: public_value(value) for key, value in original.items() if key in fields})
    return encoded(result), "explicit_public_summary"


def public_test_summary(root: Path) -> dict:
    sources = []
    primary = "results/publication/pytest.xml" if (root / "results/publication/pytest.xml").exists() else "results/v2/validation/pytest.xml"
    packaging = "results/publication/packaging_tests.xml" if (root / "results/publication/packaging_tests.xml").exists() else "results/v2/validation/pytest_packaging.xml"
    for name in (primary, packaging, "results/publication/pytest_installation.xml"):
        path = root / name
        if not path.exists():
            continue
        tree = ET.parse(path).getroot()
        suites = [tree] if tree.tag == "testsuite" else list(tree.findall("testsuite"))
        row = {"source": name, "source_sha256": digest(path.read_bytes())}
        row.update({field: sum(int(s.get(field, "0")) for s in suites) for field in ("tests", "failures", "errors", "skipped")})
        sources.append(row)
    return {"publication_summary": True, "sources": sources, "counting_note": "Packaging/installation subsets overlap with the full suite and are not added to its count. No tests are rerun by summary generation."}


def public_acceptance_summary(root: Path) -> dict:
    reports = {}
    fields = {
        "video_playback.json": {"checked_at", "kind", "metadata", "samples", "blocked_external_origins", "video_sha256", "all_passed", "project_version"},
        "preflight_windows.json": {"started_at_utc", "finished_at_utc", "kind", "not_final_release_or_remote_download", "checks", "all_passed", "confirmation"},
        "preflight_browser.json": {"started_at", "finished_at", "scope", "tests", "errors", "blocked_external", "all_passed"},
        "preflight_install.json": {"at_utc", "python_version", "fresh_venv", "copied_venv", "installation_command", "cache_policy", "checks_passed"},
        "preflight_artifact_verification.json": {"verified_at_utc", "offline", "artifacts"},
        "preflight_resource_reuse.json": {"at_utc", "method", "all_passed"},
        "preflight_visual_review.json": {"at_utc", "scope", "all_passed"},
    }
    for name, keep in fields.items():
        path = root / "results/publication" / name
        if not path.is_file():
            continue
        raw = path.read_bytes(); value = json.loads(raw.decode("utf-8-sig"))
        summary = summary_origin("results/publication/" + name, raw)
        summary.update({key: public_value(child) for key, child in value.items() if key in keep})
        for collection in ("checks", "tests", "samples"):
            if isinstance(summary.get(collection), (list, dict)):
                summary[collection + "_count"] = len(summary[collection])
        if name == "video_playback.json" and summary.get("video_sha256") != digest((root / "demo/demo.mp4").read_bytes()):
            raise ValueError("Current publication video playback report is stale")
        reports[name] = summary
    return {"publication_summary": True, "reports": reports, "scope": "Actual current video playback, copied-directory prepublication checks and resource reuse. These do not claim anonymous release download validation or new formal model experiments."}


def readme_links(payload: dict[str, bytes]) -> dict:
    text = payload.get("README.md", b"").decode("utf-8-sig")
    checked, missing, directories = [], [], []
    for reference in re.findall(r"!?\[[^\]]*\]\((<[^>]+>|[^)]+)\)", text):
        value = reference.strip().strip("<>")
        url = urlsplit(value)
        if url.scheme or url.netloc or not url.path:
            continue
        name = unquote(url.path).replace("\\", "/")
        if name.startswith("/") or ".." in Path(name).parts:
            missing.append(name); continue
        if name in payload:
            checked.append(name)
        elif any(p.startswith(name.rstrip("/") + "/") for p in payload):
            directories.append(name)
        else:
            missing.append(name)
    return {"all_passed": not missing, "checked_file_links": sorted(set(checked)), "directory_links": sorted(set(directories)), "missing_links": sorted(set(missing)), "scope": "README relative links in the public source ZIP; web URLs are not tested by this filesystem check."}


def plan(root: Path, validate: bool = True) -> tuple[dict[str, bytes], dict]:
    builder = module("build_package")
    selected = builder.select_files(root, "light")[0]
    if validate:
        builder.validate_delivery(root, "light", selected)
    payload, entries, excluded = {}, {}, {}
    for path in selected:
        name = path.relative_to(root).as_posix()
        reason = public_exclusion(name)
        if reason:
            excluded[name] = reason
            continue
        raw = path.read_bytes()
        content, kind = project_file(name, raw)
        payload[name] = content
        entries[name] = {"bytes": len(content), "sha256": digest(content), "source_sha256": digest(raw), "kind": kind}
    # Every published digest must survive Windows checkout and anonymous ZIPs.
    # This changes only the independent snapshot, not the source .gitattributes.
    if ".gitattributes" in payload and b"# Publication snapshot: preserve all manifest-bound bytes" not in payload[".gitattributes"]:
        payload[".gitattributes"] += b"\n# Publication snapshot: preserve all manifest-bound bytes\n* -text\n"
        entries[".gitattributes"].update(bytes=len(payload[".gitattributes"]), sha256=digest(payload[".gitattributes"]), kind="public_exact_byte_checkout_attributes")
    # Preserve strong browser index bindings after explicitly summarizing targets.
    index_name = "results/v2/browser/ui_acceptance.json"
    if index_name in payload:
        index = json.loads(payload[index_name])
        for item in index.get("browser_reports", []):
            name = item["path"].replace("\\", "/")
            if name not in payload:
                raise ValueError("Public browser index target excluded: " + name)
            item["sha256"] = digest(payload[name]); item["bytes"] = len(payload[name])
        payload[index_name] = encoded(index)
        entries[index_name].update(bytes=len(payload[index_name]), sha256=digest(payload[index_name]))
    test_name = "results/publication/test_summary.json"
    payload[test_name] = encoded(public_test_summary(root))
    entries[test_name] = {"bytes": len(payload[test_name]), "sha256": digest(payload[test_name]), "kind": "explicit_public_test_summary"}
    acceptance_name = "results/publication/acceptance_summary.json"
    payload[acceptance_name] = encoded(public_acceptance_summary(root))
    entries[acceptance_name] = {"bytes": len(payload[acceptance_name]), "sha256": digest(payload[acceptance_name]), "kind": "explicit_current_public_acceptance_summary"}
    try:
        source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, stderr=subprocess.PIPE).decode().strip()
        tracked = set(subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode("utf-8").split("\0"))
        modified = set(subprocess.check_output(["git", "diff", "--name-only", "HEAD", "-z"], cwd=root).decode("utf-8").split("\0"))
    except (OSError, subprocess.CalledProcessError):
        old = json.loads((root / "configs/publication.json").read_text(encoding="utf-8")) if (root / "configs/publication.json").exists() else {}
        source_commit, tracked, modified = old.get("source_commit"), set(), set()
    for name, info in entries.items():
        info["source_tracking"] = "modified_since_source_commit" if name in modified else "tracked_at_source_commit" if name in tracked else "additional_working_tree_artifact"
    marker = {"public_distribution": True, "source_commit": source_commit, "history_strategy": "independent_allowlist_snapshot_original_history_preserved", "default_repackage": ".venv/Scripts/python.exe scripts/build_package.py", "source_audit": "results/publication/history_audit_public.json"}
    payload["configs/publication.json"] = encoded(marker)
    entries["configs/publication.json"] = {"sha256": digest(payload["configs/publication.json"]), "bytes": len(payload["configs/publication.json"]), "kind": "public_snapshot_marker"}
    counts = {group: sum(name.startswith(f"results/{group}/records/") and name.endswith(".json") for name in payload) for group in builder.FORMAL_COUNTS}
    if validate and counts != builder.FORMAL_COUNTS:
        raise ValueError("Public allowlist does not retain all 3672 formal records")
    audit = module("audit_publication")
    candidates, warnings = {}, {}
    for name, content in payload.items():
        findings = audit.scan_content(content)
        risky = {k: v for k, v in findings.items() if k.startswith("credential_candidate:")}
        if risky:
            candidates[name] = risky
        if findings.get("private_environment_path"):
            warnings[name] = {"private_environment_path": findings["private_environment_path"]}
    links = readme_links(payload)
    report = {"schema_version": 1, "source_commit": source_commit, "source_history_unchanged": True, "original_evidence_unchanged": True, "files": entries, "excluded": excluded, "formal_record_counts": counts, "credential_candidates": candidates, "private_path_warnings": warnings, "readme_source_zip_links": links, "all_original_deliverables_validated": validate, "license_policy": "No license is invented for project-owned code. Third-party data licenses and selection provenance retain their original scope; code licenses are not assumed to license dataset prose."}
    if validate and candidates:
        raise ValueError("Public credential-pattern candidates require review (paths only): " + ", ".join(sorted(candidates)))
    if validate and not links["all_passed"]:
        raise ValueError("Public source ZIP README has missing relative links: " + ", ".join(links["missing_links"]))
    return payload, report


def prepare(root: Path, destination: Path) -> dict:
    root, destination = root.resolve(), destination.resolve()
    if destination.exists():
        raise ValueError("Public snapshot destination must be a new directory; existing files are never overwritten")
    payload, report = plan(root)
    destination.mkdir(parents=True)
    for name, content in payload.items():
        target = (destination / name).resolve()
        if not target.is_relative_to(destination):
            raise ValueError("Public allowlist path escaped destination")
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
    (destination / "PUBLICATION_MANIFEST.json").write_bytes(encoded(report))
    builder = module("build_package")
    builder.validate_delivery(destination, "light", builder.select_files(destination, "light")[0])
    for name, meta in report["files"].items():
        if digest((destination / name).read_bytes()) != meta["sha256"]:
            raise ValueError("Prepared public snapshot does not match its allowlist")
    output = root / "results/publication"
    output.mkdir(parents=True, exist_ok=True)
    names = sorted(set(payload) | {"PUBLICATION_MANIFEST.json"})
    (output / "public_git_pathspec.nul").write_bytes(b"\0".join(name.encode("utf-8") for name in names) + b"\0")
    (output / "public_manifest.json").write_bytes(encoded(report))
    return {"snapshot": str(destination), "source_commit": report["source_commit"], "files": len(names), "bytes": sum(len(v) for v in payload.values()), "formal_record_counts": report["formal_record_counts"], "git_initialized": False, "git_committed": False, "git_pushed": False, "force_add_pathspec": str(output / "public_git_pathspec.nul")}


def verify_tracking(root: Path) -> dict:
    manifest = json.loads((root / "PUBLICATION_MANIFEST.json").read_text(encoding="utf-8"))
    tracked = set(subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode("utf-8").split("\0"))
    expected = set(manifest["files"]) | {"PUBLICATION_MANIFEST.json"}
    missing = sorted(expected - tracked)
    if missing:
        raise ValueError("Public allowlist files not actually tracked: " + ", ".join(missing[:20]))
    extras = sorted(tracked - expected - {""})
    if extras:
        raise ValueError("Tracked files outside public allowlist: " + ", ".join(extras[:20]))
    staged = {}
    for row in subprocess.check_output(["git", "ls-files", "--stage", "-z"], cwd=root).split(b"\0"):
        if row:
            metadata, name = row.split(b"\t", 1)
            mode, oid, stage = metadata.split()
            if stage != b"0":
                raise ValueError("Unmerged index entry in public snapshot")
            staged[name.decode("utf-8")] = oid.decode("ascii")
    object_format = subprocess.check_output(["git", "rev-parse", "--show-object-format"], cwd=root).decode().strip()
    for name, value in manifest["files"].items():
        raw = (root / name).read_bytes()
        if digest(raw) != value["sha256"]:
            raise ValueError("Tracked public artifact has changed: " + name)
        git_digest = hashlib.new(object_format, b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        if staged.get(name) != git_digest:
            raise ValueError("Git index bytes differ from the public artifact (stage current exact bytes): " + name)
    return {"all_passed": True, "tracked_files": len(expected), "formal_record_counts": manifest["formal_record_counts"], "scope": "Git index identities match actual manifest-bound bytes; remote push verification is separate."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--check-tracked", action="store_true")
    args = parser.parse_args(argv)
    if args.check_tracked:
        result = verify_tracking(args.root.resolve())
    elif args.preview:
        payload, report = plan(args.root.resolve(), validate=False)
        out = args.root / "results/publication"; out.mkdir(parents=True, exist_ok=True)
        (out / "public_allowlist_preview.json").write_bytes(encoded(report))
        result = {"preview_only": True, "files": len(payload), "formal_record_counts": report["formal_record_counts"], "credential_candidate_paths": sorted(report["credential_candidates"]), "private_path_warning_paths": sorted(report["private_path_warnings"]), "missing_required_files": [name for name in module("build_package").required_files("light") if name not in payload]}
    else:
        destination = args.destination or args.root / "dist/publication" / ("public_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        result = prepare(args.root, destination)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
