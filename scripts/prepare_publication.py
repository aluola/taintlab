"""Prepare reviewed staging and synchronize an existing public history safely.

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
    if name.startswith("results/core_features/") and name.endswith(".xml"):
        original = ET.fromstring(content)
        suites = [original] if original.tag == "testsuite" else list(original.findall("testsuite"))
        result = ET.Element("testsuites", {"publication_summary": "true", "source_evidence_path": name, "original_evidence_sha256": digest(content), "disclosure": "Saved JUnit counts/case identities; hostnames, properties and console/failure output omitted. Not a new test run."})
        for suite in suites:
            public = ET.SubElement(result, "testsuite", {key: value for key, value in suite.attrib.items() if key in {"name", "errors", "failures", "skipped", "tests", "time", "timestamp"}})
            for case in suite.findall("testcase"):
                child = ET.SubElement(public, "testcase", {key: value for key, value in case.attrib.items() if key in {"name", "classname", "time"}})
                for status in ("failure", "error", "skipped"):
                    if case.find(status) is not None:
                        ET.SubElement(child, status, {"message": "See saved original evidence; details omitted from public summary"})
        return ET.tostring(result, encoding="utf-8", xml_declaration=True), "explicit_public_junit_summary"
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
    primary = next((p for p in ("results/core_features/validation/pytest_release.xml", "results/core_features/pytest.xml", "results/core_features/validation/pytest.xml", "results/publication/pytest.xml") if (root / p).exists()), "results/v2/validation/pytest.xml")
    packaging = next((p for p in ("results/core_features/packaging_tests.xml", "results/core_features/validation/packaging_tests.xml", "results/publication/packaging_tests.xml") if (root / p).exists()), "results/v2/validation/pytest_packaging.xml")
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
        if name == "video_playback.json" and (root / "demo/core_features/visual_review.json").exists():
            path = root / "demo/playback_validation.json"
        if not path.is_file():
            continue
        raw = path.read_bytes(); value = json.loads(raw.decode("utf-8-sig"))
        summary = summary_origin(path.relative_to(root).as_posix(), raw)
        summary["evidence_context"] = "current_feature_demo" if name == "video_playback.json" and path.parent.name == "demo" else "saved_prior_publication_evidence"
        summary.update({key: public_value(child) for key, child in value.items() if key in keep})
        for collection in ("checks", "tests", "samples"):
            if isinstance(summary.get(collection), (list, dict)):
                summary[collection + "_count"] = len(summary[collection])
        if name == "video_playback.json" and summary.get("video_sha256") != digest((root / "demo/demo.mp4").read_bytes()):
            raise ValueError("Current publication video playback report is stale")
        reports[name] = summary
    return {"publication_summary": True, "reports": reports, "scope": "The playback entry binds the currently delivered video. Prior publication preflight/install evidence is explicitly marked as historical; summary generation performs no new acceptance or formal model runs."}


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


def rebind_feature_review_references(payload: dict[str, bytes], entries: dict) -> None:
    """Bind published review references to the explicit public summaries.

    Original source hashes remain visible, and source files are never rewritten.
    A stale source reference is rejected before any public hash is substituted.
    """
    name = "demo/core_features/visual_review.json"
    if name not in payload:
        return
    review = json.loads(payload[name])
    references = review.get("technical_evidence")
    if not references:
        return
    if not isinstance(references, dict):
        raise ValueError("Feature visual review technical evidence must be an object")
    source_review_sha256 = entries[name]["source_sha256"]
    for item in references.values():
        target = item.get("path") if isinstance(item, dict) else None
        if target not in payload:
            raise ValueError("Feature visual review public target is missing: " + str(target))
        expected_source = entries[target].get("source_sha256")
        if item.get("sha256") != expected_source:
            raise ValueError("Feature visual review source evidence hash is stale: " + target)
        item["original_source_sha256"] = expected_source
        item["sha256"] = digest(payload[target])
    review["publication_reference_projection"] = {
        "source_review_sha256": source_review_sha256,
        "scope": "Reference SHA256 values bind the published evidence bytes; original_source_sha256 retains the saved local evidence identity. Review observations are unchanged. This is not a new visual review.",
    }
    payload[name] = encoded(review)
    entries[name].update(bytes=len(payload[name]), sha256=digest(payload[name]), kind="public_review_reference_projection")

    # The current final-recording index uses a path without a review hash, but
    # preserve correctness when a source index explicitly binds that hash.
    index_name = "demo/final_recording_metadata.json"
    if index_name in payload:
        index = json.loads(payload[index_name])
        if index.get("visual_review") == name and "visual_review_sha256" in index:
            if index["visual_review_sha256"] != source_review_sha256:
                raise ValueError("Final recording source visual review hash is stale")
            index["visual_review_original_source_sha256"] = source_review_sha256
            index["visual_review_sha256"] = digest(payload[name])
            payload[index_name] = encoded(index)
            entries[index_name].update(bytes=len(payload[index_name]), sha256=digest(payload[index_name]), kind="public_review_index_reference_projection")


def plan(root: Path, validate: bool = True) -> tuple[dict[str, bytes], dict]:
    builder = module("build_package")
    selected = builder.select_files(root, "light")[0]
    if validate:
        builder.validate_delivery(root, "light", selected)
    payload, entries, excluded = {}, {}, {}
    for path in selected:
        name = path.relative_to(root).as_posix()
        if name == "PUBLICATION_MANIFEST.json":
            excluded[name] = "regenerated_manifest_does_not_hash_itself"
            continue
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
    rebind_feature_review_references(payload, entries)
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
    marker = {"public_distribution": True, "source_commit": source_commit, "history_strategy": "allowlist_staging_for_existing_public_history", "default_repackage": ".venv/Scripts/python.exe scripts/build_package.py", "source_audit": "results/publication/history_audit_public.json", "release_commit_binding": "The delivery manifest records the existing merged public main commit; source_commit continues to identify the original source checkout."}
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
    manifest_raw = (root / "PUBLICATION_MANIFEST.json").read_bytes()
    manifest_oid = hashlib.new(object_format, b"blob " + str(len(manifest_raw)).encode("ascii") + b"\0" + manifest_raw).hexdigest()
    if staged.get("PUBLICATION_MANIFEST.json") != manifest_oid:
        raise ValueError("Git index bytes differ from the current PUBLICATION_MANIFEST.json")
    return {"all_passed": True, "tracked_files": len(expected), "formal_record_counts": manifest["formal_record_counts"], "scope": "Git index identities match actual manifest-bound bytes; remote push verification is separate."}


def git_read(root: Path, *arguments: str) -> bytes:
    """Only callers using explicit read-only Git commands are defined here."""
    return subprocess.check_output(["git", *arguments], cwd=root, stderr=subprocess.PIPE)


def verify_public_main(root: Path) -> dict:
    head = git_read(root, "rev-parse", "HEAD").decode().strip()
    main = git_read(root, "rev-parse", "refs/remotes/origin/main^{commit}").decode().strip()
    if head != main:
        raise ValueError("Public release packaging requires the fetched origin/main commit after PR merge")
    if git_read(root, "status", "--porcelain", "--untracked-files=all", "-z"):
        raise ValueError("Public release packaging requires committed files and a clean checkout")
    return {"head": head, "fetched_origin_main": main, "matches_fetched_main": True, "clean_checkout": True, "remote_pr_merge_verified_here": False, "scope": "Local read-only Git binding. Fetching and checking the actual merged PR and remote tree are separate publication steps."}


def safe_public_name(name: str) -> Path:
    path = Path(name)
    if not name or "\\" in name or ":" in name or path.is_absolute() or ".." in path.parts or any(ord(c) < 32 for c in name):
        raise ValueError("Unsafe publication path")
    if module("build_package").global_file_exclusion(path) or public_exclusion(name):
        raise ValueError("Excluded publication path: " + name)
    return path


def synchronization_plan(staging: Path, target: Path, base_ref: str = "origin/main", baseline_ref: str = "v2.0.0") -> dict:
    """Three-way compare the last published manifest, desired staging and branch.

    No deletion is inferred. A remote-only edit survives; a dual edit is a
    conflict. Even a byte-for-byte desired formal-record change is prohibited.
    This does not fetch, create branches, stage, commit, tag, merge or push.
    """
    staging, target = staging.resolve(), target.resolve()
    if staging == target or staging.is_relative_to(target) or target.is_relative_to(staging):
        raise ValueError("Staging and public checkout must be separate directories")
    manifest_path = staging / "PUBLICATION_MANIFEST.json"
    desired = json.loads(manifest_path.read_text(encoding="utf-8"))
    head = git_read(target, "rev-parse", "HEAD").decode().strip()
    base = git_read(target, "rev-parse", base_ref + "^{commit}").decode().strip()
    baseline = git_read(target, "rev-parse", baseline_ref + "^{commit}").decode().strip()
    # A branch must actually descend from the fetched public main. Fetching is
    # deliberately a separate maintainer action so this script is offline.
    if subprocess.run(["git", "merge-base", "--is-ancestor", base, head], cwd=target, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode:
        raise ValueError("Public checkout is not based on the requested public main")
    if git_read(target, "status", "--porcelain", "--untracked-files=all", "-z"):
        raise ValueError("Public checkout must have no staged, modified or untracked work before synchronization")
    old = json.loads(git_read(target, "show", baseline + ":PUBLICATION_MANIFEST.json"))
    tracked = {p for p in git_read(target, "ls-files", "-z").decode("utf-8").split("\0") if p}
    builder = module("build_package")
    changes, conflicts, current, resulting = [], [], {}, {}
    for name in sorted(tracked | set(desired["files"])):
        if name == "PUBLICATION_MANIFEST.json":
            continue
        rel = safe_public_name(name)
        existing = target / rel
        if not existing.resolve().is_relative_to(target) or not (staging / rel).resolve().is_relative_to(staging):
            raise ValueError("Publication path traverses a directory outside its checkout")
        if existing.is_symlink() or (existing.exists() and not existing.is_file()):
            raise ValueError("Nonregular public artifact: " + name)
        current_hash = digest(existing.read_bytes()) if existing.is_file() else None
        current[name] = current_hash
        wanted = desired["files"].get(name)
        previous = old["files"].get(name)
        wanted_hash = wanted.get("sha256") if wanted else None
        old_hash = previous.get("sha256") if previous else None
        if wanted:
            source = staging / rel
            if source.is_symlink() or not source.is_file() or digest(source.read_bytes()) != wanted_hash:
                raise ValueError("Staging file differs from reviewed manifest: " + name)
        protected = any(name.startswith(f"results/{group}/records/") for group in builder.FORMAL_COUNTS)
        if protected and (not previous or current_hash != old_hash or wanted_hash != old_hash):
            conflicts.append({"path": name, "reason": "formal_record_bytes_are_immutable"}); continue
        if wanted_hash == current_hash and wanted_hash is not None:
            action = "unchanged"
        elif wanted is None:
            # Remote additions and previously published files are never deleted.
            action = "preserve_remote"
        elif wanted_hash == old_hash and current_hash is not None:
            action = "preserve_remote"
        elif current_hash == old_hash:
            action = "add" if current_hash is None else "update"
        else:
            conflicts.append({"path": name, "reason": "both_source_and_public_branch_changed"}); continue
        if action == "preserve_remote":
            if current_hash is None:
                conflicts.append({"path": name, "reason": "public_branch_removed_requested_artifact"}); continue
            if builder.light_reason(rel, set()) is None:
                conflicts.append({"path": name, "reason": "remote_file_needs_explicit_allowlist_review"}); continue
            raw = existing.read_bytes()
            candidates = module("audit_publication").scan_content(raw)
            if any(key.startswith("credential_candidate:") for key in candidates):
                conflicts.append({"path": name, "reason": "remote_credential_pattern_requires_review"}); continue
            resulting[name] = {"bytes": len(raw), "sha256": current_hash, "kind": "preserved_public_branch_file", "public_branch_commit": head}
        else:
            resulting[name] = dict(wanted)
        changes.append({"path": name, "action": action, "previous_published_sha256": old_hash, "branch_sha256": current_hash, "staging_sha256": wanted_hash})
    return {"schema_version": 1, "kind": "existing_public_history_three_way_sync", "staging_directory": str(staging), "target_directory": str(target), "staging_manifest_sha256": digest(manifest_path.read_bytes()), "target_head": head, "base_ref": base_ref, "base_commit": base, "baseline_ref": baseline_ref, "baseline_commit": baseline, "source_commit": desired.get("source_commit"), "current_files": current, "files": resulting, "changes": changes, "conflicts": conflicts, "all_passed": not conflicts, "deletions": [], "git_mutations": False, "scope": "Read-only comparison. Remote-only changes are retained; dual edits and formal-record changes require manual resolution. Final package must be built after the PR is merged into public main."}


def apply_synchronization(reviewed: dict) -> dict:
    """Apply an unchanged reviewed plan to files only, leaving Git to the caller."""
    staging, target = Path(reviewed["staging_directory"]), Path(reviewed["target_directory"])
    fresh = synchronization_plan(staging, target, reviewed["base_ref"], reviewed["baseline_ref"])
    if fresh != reviewed:
        raise ValueError("Synchronization inputs changed after review; produce a new plan")
    if not fresh["all_passed"]:
        raise ValueError("Synchronization has unresolved conflicts; no files were changed")
    source_manifest = json.loads((staging / "PUBLICATION_MANIFEST.json").read_text(encoding="utf-8"))
    report = dict(source_manifest)
    report.update(files=fresh["files"], synchronization={key: fresh[key] for key in ("kind", "source_commit", "target_head", "base_ref", "base_commit", "baseline_ref", "baseline_commit", "changes", "deletions", "git_mutations")})
    report["synchronization"]["history_strategy"] = "existing_public_main_branch_pr_squash_merge"
    # Validate the complete proposed result in a fresh non-Git tree before any
    # target file is written. No half-applied invalid delivery is accepted.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="taintlab-sync-validation-") as temporary:
        check = Path(temporary)
        for item in fresh["changes"]:
            name = item["path"]
            source = target / name if item["action"] == "preserve_remote" else staging / name
            out = check / name; out.parent.mkdir(parents=True, exist_ok=True); out.write_bytes(source.read_bytes())
        (check / "PUBLICATION_MANIFEST.json").write_bytes(encoded(report))
        builder = module("build_package")
        builder.validate_delivery(check, "light", builder.select_files(check, "light")[0])
        links = readme_links({name: (check / name).read_bytes() for name in report["files"]})
        if not links["all_passed"]:
            raise ValueError("Synchronized README relative links are missing")
        report["readme_source_zip_links"] = links
        # Recheck immediately before mutation, including branch/status and hashes.
        if synchronization_plan(staging, target, reviewed["base_ref"], reviewed["baseline_ref"]) != reviewed:
            raise ValueError("Synchronization inputs changed during validation")
        for item in fresh["changes"]:
            if item["action"] in {"add", "update"}:
                out = target / item["path"]; out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes((check / item["path"]).read_bytes())
        (target / "PUBLICATION_MANIFEST.json").write_bytes(encoded(report))
    names = sorted(set(report["files"]) | {"PUBLICATION_MANIFEST.json"})
    return {"all_passed": True, "source_commit": report["source_commit"], "public_base_commit": fresh["base_commit"], "files": len(names), "updated": sum(c["action"] in {"add", "update"} for c in fresh["changes"]), "preserved_remote": sum(c["action"] == "preserve_remote" for c in fresh["changes"]), "git_initialized": False, "git_staged": False, "git_committed": False, "git_pushed": False, "next_step": "Stage exactly PUBLICATION_MANIFEST files, run --check-tracked, commit/push the existing branch, create and squash-merge the PR, then build --public at the merged main commit."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--check-tracked", action="store_true")
    parser.add_argument("--staging", type=Path, help="Reviewed staging prepared by this script; never a newly initialized Git history")
    parser.add_argument("--sync-target", type=Path, help="Existing clean public branch based on fetched origin/main")
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--baseline-ref", default="v2.0.0")
    parser.add_argument("--sync-plan", type=Path, help="Write a read-only three-way comparison plan")
    parser.add_argument("--apply-sync", type=Path, help="Apply a previously reviewed plan to files, without Git mutations")
    args = parser.parse_args(argv)
    if args.apply_sync:
        result = apply_synchronization(json.loads(args.apply_sync.read_text(encoding="utf-8")))
    elif args.sync_target:
        if not args.staging or not args.sync_plan:
            parser.error("--sync-target requires --staging and --sync-plan")
        result = synchronization_plan(args.staging, args.sync_target, args.base_ref, args.baseline_ref)
        args.sync_plan.parent.mkdir(parents=True, exist_ok=True); args.sync_plan.write_bytes(encoded(result))
        result = {key: result[key] for key in ("kind", "target_head", "base_commit", "baseline_commit", "source_commit", "conflicts", "all_passed", "deletions", "git_mutations")}
    elif args.check_tracked:
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
