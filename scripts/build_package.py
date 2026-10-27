"""Build a verified light delivery by default, or explicitly request --profile full.

Selection uses directory roles, not file size. Only the standard library is needed;
an unpacked delivery can be repackaged without a Git repository or Git executable.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILDER_VERSION = "3.1.0"
ARCHIVE_ROOT = "taintlab_project"
EXCLUDED_DIRS = {".git", ".pytest_cache", "__pycache__", "node_modules", "vendor", "models", ".cache", ".mypy_cache", ".ruff_cache", ".tox", "web_private", ".validation-build"}
ROOT_FILES = {"README.md", "AGENTS.md", "MAINTENANCE.md", "维护说明.md", "pyproject.toml", "requirements.lock.txt", ".gitignore", ".gitattributes", "LICENSE", "LICENSE.md", "启动项目.cmd", "关闭项目.cmd"}
ROOT_FILES.add("PUBLICATION_MANIFEST.json")
DATA_FILES = {"test.jsonl", "dev.jsonl", "manifest.json", "frozen_manifest.json"}
FORMAL_FILES = {"experiment_manifest.json", "metrics.csv", "metrics.jsonl", "paired_scenarios.json", "summary.json"}
FORMAL_COUNTS = {"main": 972, "ablation": 324, "v2/baseline": 1296, "v2/external": 1080}
FORMAL_BACKEND_TYPES = {"local_llama_cpp"}
FRONTEND_FILES = {"package.json", "package-lock.json", "index.html", "tsconfig.json", "vite.config.ts", "build_manifest.json", ".gitignore"}
FRONTEND_QA_FILES = {"clean_install_validation.json", "clean_install_tests.json", "unit_tests.json"}
PINNED_HISTORICAL_EVIDENCE = {"results/demo/records/development_recovery.json", "results/development_v3/records/18f1f34fcc3ae112629d286a.json", "results/development_v3/experiment_manifest.json", "results/development_v3/summary.json"}
PINNED_HISTORICAL_EVIDENCE.update({
    "results/v2/demo_live/records/54c30779a254418f840ae4ff36178026.json",
    "results/v2/demo_live/records/ef96cc7e861a4098af904ece2ef6eaf0.json",
})
DEMO_FILES = {"demo.mp4", "demo_subtitles.srt", "demo_script.md", "README.md", "narration.json", "selected_evidence.json", "video_validation.json", "playback_validation.json", "final_recording_metadata.json", "recording_timing.json"}
DEMO_V2_FILES = {"demo_upload.md", "edit_decisions.json", "composition_manifest.json", "narration_synthesis.json", "visual_review.json"}
DEMO_CORE_FILES = {"selection.json", "edit_decisions.json", "composition_manifest.json", "narration_synthesis.json", "visual_review.json", "independent_visual_review.json", "first_independent_visual_review.json", "first_encode_visual_review.json", "source_inventory.json", "recording_timing.json", "README.md", "subtitles.ass"}
DOC_QA_FILES = {"document_validation.json", "structure_validation.json", "renderer_environment.json", "visual_review_page_hashes.json", "visual_review.md", "README.md", "prepare_renderer.py", "verify_documents.py"}
DOC_CURRENT_MIRRORS = {"document_validation.json", "structure_validation.json", "visual_review_page_hashes.json", "visual_review.md"}
MANUAL_FILES = {"USER_MANUAL.md", "USER_MANUAL.docx", "USER_MANUAL.pdf"}
FEATURE_DOCUMENTS = {
    "CORE_FEATURES_GUIDE": ("core_features_qa", ("Agent 攻防靶场", "不可信内容标记", "污点追踪", "权限策略控制", "自动化攻击测试", "泄露检测与综合评测")),
    "DEVELOPMENT_AND_DELIVERY": ("development_delivery_qa", ("需求分析与技术选型", "环境搭建与结构化设计", "迭代开发与代码规范", "集成测试与优化", "打包部署与文档编写", "持续维护与迭代")),
}
FEATURE_ASSET_GROUPS = {"core-features", "development-delivery"}
FEATURE_RESULT_DIRS = {"records", "demo_runs", "selftest", "performance", "validation", "acceptance", "browser", "canary", "demo"}
FEATURE_RESULT_FILES = {"baseline_integrity.json", "final_integrity.json", "formal_summary.json", "evidence_manifest.json", "acceptance.json", "validation.json", "canary_selftest.json", "performance_summary.json", "process_memory_public.jsonl", "pytest.xml", "packaging_tests.xml", "README.md"}
PUBLIC_SUMMARY_FILES = {"history_audit_public.json", "public_audit.json", "test_summary.json", "environment_summary.json", "acceptance_summary.json", "publication_validation.json"}
BROWSER_FILES = {"ui_e2e.json", "ui_followup.json", "layout_check.json", "ui_acceptance.json", "ui_visual_review.md", "model-offline-lifecycle.json", "model-offline-visual-review.json", "model-offline.json", "model-restored.json", "focused-source-graph-v2.json"}
BROWSER_TIMING_FILES = {"frame_alignment.json", "timing_review.md"}
ENVIRONMENT_FILES = {"artifact_verification.json", "chat_template.jinja", "hardware.json", "model_health.json", "model_runtime.json", "model_smoke.json", "video_tools.json"}
VALIDATION_FILES = {"clean_install.json", "delivery_acceptance.json", "experiment_integrity.json", "model_lifecycle.json", "offline_guard_selftest.json", "offline_validation.json", "package_install.json", "package_offline_validation.json", "readme_paths.json", "pytest.xml", "pytest_final.log", "ui_final_repeat.txt"}
VALIDATION_SUFFIXES = ("_validation.json", "_acceptance.json", "_integrity.json", "_lifecycle.json", "_install.json", "_paths.json", "_selftest.json")
EXCLUSION_RULES = [
    "Both profiles omit weights/vendor binaries, virtual environments, secrets, caches, PID/lock files, transient launcher state and previously built archives.",
    "Light retains source/scripts/tests/configurations, frozen data, final documents/media, all formal experiments and selected validation evidence using semantic allowlists.",
    "Light omits narration WAVs/segments, raw video takes, QA screenshots, per-page PNGs, renderer binaries, historical duplicate development runs and unselected logs.",
    "Images referenced by non-QA Markdown documents are retained even under docs/qa. Final validation reports remain while intermediate renders are omitted.",
    "All old main/ablation and current v2 baseline/external raw records, metrics, paired scenarios and manifests remain. SQLite checkpoint/confirmation/session databases are excluded. The historical development_v3 recovery source retains its version label.",
    "Only JSON/Markdown/JUnit XML under results/launcher/validation is retained from launcher data; launcher process state, logs and screenshots are omitted.",
    "Frontend source, npm lock, compiled dist and a source/artifact build manifest remain; node_modules, tsbuildinfo and Web private owners/cookies/uploads/checkpoints never enter either profile.",
]


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def output_paths(root: Path, profile: str) -> dict[str, Path]:
    if profile not in {"light", "full"}:
        raise ValueError("Unknown package profile")
    suffix = "_light" if profile == "light" else "_full_v2"
    return {"archive": root / f"dist/taintlab_project{suffix}.zip", "manifest": root / f"dist/delivery_manifest{suffix}.json", "sha256": root / f"dist/SHA256SUMS{suffix}.txt"}


def excluded_directory(name: str) -> bool:
    name = name.lower()
    return name in EXCLUDED_DIRS or name.startswith(".venv") or name.endswith(".egg-info")


def global_file_exclusion(rel: Path) -> str | None:
    name = rel.name.lower()
    if any(excluded_directory(part) for part in rel.parts):
        return "runtime_dependency_or_cache"
    if name == ".env" or name.startswith(".env.") or name == "secrets.toml":
        return "secret_configuration"
    if name == ".validation-target.txt":
        return "temporary_frontend_validation_target"
    if name.endswith((".pyc", ".pid", ".tmp", ".zip", ".sqlite", ".sqlite3", ".db", ".sqlite-wal", ".sqlite-shm", ".lock", ".lck", ".tsbuildinfo")):
        return "generated_archive_cache_or_process_file"
    if name.startswith(("delivery_manifest", "sha256sums", "package_sha256sums")):
        return "previous_package_manifest"
    if name in {"launcher_state.json", "launcher-state.json", "process_state.json", "session_state.json"}:
        return "transient_launcher_state"
    if rel.as_posix() in {"results/confirmation_ledger.sqlite", "results/environment/llama.stderr.log", "results/environment/llama.stdout.log", "results/ui.stdout.log", "results/ui.stderr.log"}:
        return "active_process_log_or_confirmation_ledger"
    return None


def local_reference(root: Path, value: str, base: Path | None = None) -> Path | None:
    value = value.strip().strip("<>")
    if not value or (urlsplit(value).scheme and not Path(value).is_absolute()):
        return None
    value = unquote(value.split("#", 1)[0])
    for candidate in (root / value, (base or root) / value):
        resolved = candidate.resolve()
        if resolved.is_relative_to(root.resolve()) and resolved.is_file():
            return resolved.relative_to(root.resolve())
    return None


def referenced_document_images(root: Path) -> set[Path]:
    images = set()
    for markdown in (root / "docs").rglob("*.md"):
        if "qa" in markdown.relative_to(root / "docs").parts:
            continue
        source = markdown.read_text(encoding="utf-8-sig")
        references = re.findall(r"!\[[^\]]*\]\((<[^>]+>|[^)]+)\)", source)
        references += re.findall(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", source, flags=re.I)
        for reference in references:
            reference = re.split(r"\s+[\"']", reference, maxsplit=1)[0]
            rel = local_reference(root, reference, markdown.parent)
            if rel and rel.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".pdf"}:
                images.add(rel)
    return images


def validation_report_name(name: str) -> bool:
    lowered = name.lower()
    return not any(marker in lowered for marker in ("_previous", "_before", "_initial")) and (name in VALIDATION_FILES or lowered.endswith(VALIDATION_SUFFIXES) or lowered.endswith(".xml"))


def browser_report_allowed(rel: Path) -> bool:
    if rel.parts[:3] != ("results", "v2", "browser") or global_file_exclusion(rel):
        return False
    if len(rel.parts) == 4:
        return rel.name in BROWSER_FILES or bool(re.fullmatch(r"ui_(?:e2e|followup)_\d{4}-\d{2}-\d{2}T[\d-]+Z\.json", rel.name))
    return rel.parts[3:4] == ("video_timing",) and len(rel.parts) == 5 and rel.name in BROWSER_TIMING_FILES


def browser_index_references(document: dict) -> list[dict]:
    """Follow report references, never screenshot/raw media or arbitrary state."""
    references = []
    keys = {"path", "report", "evidence_report", "follow_up", "review_record", "recording_timing_review"}
    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in keys and isinstance(child, str) and child.replace("\\", "/").startswith("results/v2/browser/") and Path(child).suffix.lower() in {".json", ".md"}:
                    digest = value.get("sha256") if key == "path" else value.get("review_sha256") if key == "review_record" else None
                    references.append({"path": child.replace("\\", "/"), "sha256": digest})
                elif isinstance(child, (dict, list)):
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(document)
    return references


def validate_browser_evidence(root: Path, chosen: set[str], expected_version: str) -> dict:
    document = read_json(root / "results/v2/browser/ui_acceptance.json")
    if document.get("version") != expected_version or document.get("all_targeted_checks_passed_latest_evidence") is not True:
        raise ValueError("Current browser acceptance version or conclusion is invalid")
    checked = {}
    for item in browser_index_references(document):
        rel = local_reference(root, item["path"])
        if rel is None or not browser_report_allowed(rel) or rel.as_posix() not in chosen:
            raise ValueError("Browser acceptance report reference missing or excluded: " + item["path"])
        actual = sha(root / rel)
        if item["sha256"] is not None and item["sha256"] != actual:
            raise ValueError("Browser acceptance report SHA256 mismatch: " + item["path"])
        checked[rel.as_posix()] = actual
    return {"passed": True, "reports": checked, "scope": "Acceptance report references only. Unreferenced screenshots and raw media are intentionally not redistributed."}


def validate_production_evidence(root: Path, chosen: set[str], expected_version: str) -> dict:
    current = "core_features" if (root / "demo/core_features/visual_review.json").is_file() else "v2"
    prefix = "demo/" + current
    review = read_json(root / prefix / "visual_review.json")
    if review.get("project_version") != expected_version or not (review.get("all_passed") is True or review.get("passed") is True) or review.get("passed") is False or review.get("all_passed") is False:
        raise ValueError("Current video visual review version or conclusion is invalid")
    if review.get("video_sha256") != sha(root / "demo/demo.mp4"):
        raise ValueError("Current video visual review SHA256 is stale")
    composition = read_json(root / prefix / "composition_manifest.json")
    edit = read_json(root / prefix / "edit_decisions.json")
    if any(item.get("project_version") != expected_version for item in (composition, edit)) or composition.get("edl_sha256") != sha(root / prefix / "edit_decisions.json"):
        raise ValueError("Current video composition/edit-decision evidence is stale")
    narration = read_json(root / prefix / "narration_synthesis.json")
    if narration.get("narration_sha256") != sha(root / "demo/narration.json"):
        raise ValueError("Current narration synthesis evidence is stale")
    recordings = sorted(name for name in chosen if Path(name).parts[:3] == ("demo", current, "recordings") and Path(name).suffix == ".json")
    if not recordings:
        raise ValueError("No current video recording metadata selected")
    for name in recordings:
        record = read_json(root / name)
        if record.get("version") != expected_version:
            raise ValueError("Video recording metadata has a different version")
        for field, hash_field in (("selection_file", "selection_sha256"), ("upload_file", "upload_sha256")):
            rel = local_reference(root, record.get(field, "").replace("\\", "/"))
            if rel is None or rel.as_posix() not in chosen or record.get(hash_field) != sha(root / rel):
                raise ValueError("Video recording source metadata missing or stale: " + field)
    for name in DOC_CURRENT_MIRRORS:
        if sha(root / "docs/qa" / name) != sha(root / "docs/v2/qa" / name):
            raise ValueError("Current document QA mirrors disagree: " + name)
    feature_chapters = validate_feature_video(root, chosen, edit, review) if current == "core_features" else None
    return {"passed": True, "production_directory": prefix, "video_sha256": review["video_sha256"], "recording_reports": recordings, "document_qa_mirrors": sorted(DOC_CURRENT_MIRRORS), "feature_chapters": feature_chapters}


def validate_feature_video(root: Path, chosen: set[str], edit: dict, review: dict) -> dict:
    for name in ("source_inventory.json", "recording_timing.json"):
        relative = "demo/core_features/" + name
        if relative not in chosen or not (root / relative).is_file() or not read_json(root / relative):
            raise ValueError("Feature video reproduction metadata is missing: " + relative)
    duration = read_json(root / "demo/video_validation.json").get("actual_duration")
    if not isinstance(duration, (int, float)) or not 180 <= duration <= 300:
        raise ValueError("Current feature video must have an actually measured 180–300 second duration")
    chapters = edit.get("feature_chapters", [])
    if not isinstance(chapters, list) or [item.get("id") for item in chapters if isinstance(item, dict)] != [f"F{i:02d}" for i in range(1, 7)]:
        raise ValueError("Current feature video needs six ordered F01–F06 operation/result chapters")
    previous_end = 0.0
    for chapter in chapters:
        start, end = chapter.get("start_seconds"), chapter.get("end_seconds")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or not previous_end <= start < end <= duration:
            raise ValueError("Feature video chapter timing is invalid or exceeds the actual video")
        previous_end = end
        for field in ("operation_evidence", "result_evidence"):
            references = chapter.get(field)
            if not isinstance(references, list) or not references:
                raise ValueError("Feature video chapter lacks " + field)
            for reference in references:
                if not isinstance(reference, dict):
                    raise ValueError("Invalid feature video evidence reference")
                rel = local_reference(root, reference.get("path", ""))
                if rel is None or rel.as_posix() not in chosen or reference.get("sha256") != sha(root / rel):
                    raise ValueError("Feature video operation/result evidence is missing or stale")
    if not review.get("release_version") or review.get("release_version") != edit.get("release_version"):
        raise ValueError("Feature video release and runtime versions must be explicitly distinguished")
    return {"passed": True, "actual_duration": duration, "chapters": [item["id"] for item in chapters], "release_version": review["release_version"], "scope": "Validates declared actual operation/result evidence and timing; does not replace viewing the completed video."}


def selected_demo_records(document: dict) -> list[dict]:
    """Read explicit records arrays recursively, with legacy keyed-map support.

    Metadata/notes are not records. Malformed entries must not silently vanish
    from selection or validation just because a collection has another shape.
    """
    if not isinstance(document, dict):
        raise ValueError("Selected demo evidence must be a JSON object")
    if "records" not in document:
        return [v for v in document.values() if isinstance(v, dict) and "path" in v]
    if not isinstance(document["records"], list) or not document["records"]:
        raise ValueError("Selected demo records must be a non-empty array")
    records = []

    def visit(value):
        if isinstance(value, dict) and "path" in value:
            if not isinstance(value["path"], str) or not value["path"].strip():
                raise ValueError("Selected demo record path must be a non-empty string")
            records.append(value)
            return
        children = value if isinstance(value, list) else [v for v in value.values() if isinstance(v, (dict, list))] if isinstance(value, dict) else []
        if not children:
            raise ValueError("Selected demo records contain an entry without a path")
        for child in children:
            visit(child)

    visit(document["records"])
    return records


def demo_record_allowed(rel: Path) -> bool:
    return bool(rel.parts and rel.parts[0] == "results" and rel.suffix.lower() == ".json" and ("records" in rel.parts or rel.parts[:3] in {("results", "v2", "acceptance"), ("results", "v2", "demo"), ("results", "core_features", "demo_runs")}) and not global_file_exclusion(rel))


def validate_demo_evidence(root: Path, chosen: set[str] | None = None, expected_version: str | None = None) -> dict:
    document = read_json(root / "demo/selected_evidence.json")
    modern = "records" in document
    if modern and expected_version is not None and document.get("project_version") != expected_version:
        raise ValueError("Selected demo evidence has a different project version")
    checked = []
    for item in selected_demo_records(document):
        rel = local_reference(root, item["path"])
        if rel is None or not demo_record_allowed(rel) or (chosen is not None and rel.as_posix() not in chosen):
            raise ValueError("Selected demo record is missing or excluded: " + item["path"])
        declared = item.get("sha256")
        if (modern or declared is not None) and (not isinstance(declared, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", declared)):
            raise ValueError("Selected demo record requires a valid SHA256: " + item["path"])
        actual = sha(root / rel)
        if declared is not None and actual != declared.lower():
            raise ValueError("Selected demo record SHA256 mismatch: " + item["path"])
        checked.append({"path": rel.as_posix(), "sha256": actual, "declared_hash_checked": declared is not None})
    return {"schema": "records_array" if modern else "legacy_keyed_map", "records": checked, "checked_records": len(checked), "passed": True}


def referenced_evidence(root: Path) -> set[Path]:
    selected = {Path(p) for p in PINNED_HISTORICAL_EVIDENCE if (root / p).is_file()}
    browser_index = root / "results/v2/browser/ui_acceptance.json"
    if browser_index.is_file():
        for item in browser_index_references(read_json(browser_index)):
            rel = local_reference(root, item["path"])
            if rel and browser_report_allowed(rel):
                selected.add(rel)
    evidence_file = root / "demo/selected_evidence.json"
    if evidence_file.exists():
        for item in selected_demo_records(read_json(evidence_file)):
            rel = local_reference(root, item.get("path", ""))
            if rel and demo_record_allowed(rel):
                selected.add(rel)
                campaign = rel.parent.parent
                selected.update(campaign / name for name in ("experiment_manifest.json", "summary.json") if (root / campaign / name).exists())
                original = local_reference(root, read_json(root / rel).get("source_record_path", ""))
                if original and original.parts[:3] == ("results", "development_v3", "records"):
                    selected.add(original)
                    selected.update(Path("results/development_v3") / name for name in ("experiment_manifest.json", "summary.json"))
    reports = list((root / "results/validation").glob("*.json")) + list((root / "results/v2/validation").glob("*.json"))
    for report in reports:
        if not validation_report_name(report.name):
            continue
        for run in read_json(report).get("runs", []):
            rel = local_reference(root, run.get("trace", ""))
            if rel and (rel.parts[:2] == ("results", "validation") or rel.parts[:3] == ("results", "v2", "validation")) and rel.name.startswith("offline_"):
                selected.add(rel)
    return {path for path in selected if (root / path).is_file()}


def light_reason(rel: Path, references: set[Path]) -> str | None:
    parts, name = rel.parts, rel.name
    if rel.suffix.lower() == ".log":
        return None
    if rel.as_posix() in PINNED_HISTORICAL_EVIDENCE:
        return "pinned_historical_demo_evidence"
    if rel in references:
        return "referenced_document_image_or_selected_evidence"
    if len(parts) == 1 and name in ROOT_FILES:
        return "project_entry_or_metadata"
    if parts[0] in {"src", "scripts", "tests", "configs", "members"}:
        return "source_configuration_tests_or_members"
    if parts[0] == "frontend" and ((len(parts) == 2 and name in FRONTEND_FILES) or parts[1:2] in (("src",), ("dist",), ("public",), ("scripts",))):
        return "frontend_source_compiled_assets_or_npm_lock"
    if parts[:2] == ("frontend", "qa") and len(parts) == 3 and name in FRONTEND_QA_FILES:
        return "frontend_clean_install_and_unit_test_evidence"
    if rel.as_posix() == ".streamlit/config.toml":
        return "local_ui_configuration"
    if len(parts) == 2 and parts[0] == "data" and name in DATA_FILES:
        return "frozen_or_development_dataset"
    if parts[:2] == ("data", "v2") and rel.suffix.lower() in {".json", ".jsonl", ".txt", ".md", ".xml", ".csv"}:
        return "v2_frozen_dataset_source_license_or_generation_evidence"
    if parts[:3] == ("data", "demo", "core_features") and rel.suffix.lower() in {".json", ".jsonl", ".txt", ".md", ".csv", ".pdf", ".docx"}:
        return "independent_core_feature_mock_examples_not_formal_dataset"
    if parts[0] == "docs":
        if len(parts) == 2 and name in MANUAL_FILES:
            return "current_user_manual"
        if parts[:3] == ("docs", "assets", "user-manual") and rel.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".json", ".md", ".yaml", ".yml", ".drawio"}:
            return "user_manual_original_annotated_images_and_build_configuration"
        if len(parts) == 2 and any(name == stem + "." + suffix for stem in FEATURE_DOCUMENTS for suffix in ("md", "pdf", "docx")):
            return "six_chapter_feature_or_development_document"
        if parts[:2] == ("docs", "assets") and len(parts) > 3 and parts[2] in FEATURE_ASSET_GROUPS and rel.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".json", ".md", ".yaml", ".yml", ".drawio", ".py"}:
            return "core_feature_final_figures_and_reproduction_configuration"
        if len(parts) > 2 and parts[1] in {item[0] for item in FEATURE_DOCUMENTS.values()} and rel.suffix.lower() in {".json", ".md"}:
            return "six_chapter_document_quality_evidence"
        if parts[:3] == ("docs", "publication", "manual_qa") and rel.suffix.lower() in {".json", ".md"}:
            return "user_manual_final_quality_evidence"
        if len(parts) == 2 and rel.suffix.lower() in {".md", ".csv"}:
            return "project_document_or_member_table"
        if parts[:2] == ("docs", "qa") and len(parts) == 3 and name in DOC_QA_FILES:
            return "document_validation_or_reproduction_helper"
        if parts[:3] == ("docs", "v2", "qa") and len(parts) == 4 and (name in DOC_QA_FILES or re.fullmatch(r"visual_review_pages_\d+_\d+\.json", name)):
            return "current_v2_document_validation"
        if "qa" not in parts and rel.suffix.lower() == ".md":
            return "project_document"
    if parts[0] == "dist" and len(parts) == 2 and name in {"project_report.docx", "project_report.pdf"}:
        return "final_report"
    if parts[0] == "demo":
        if len(parts) == 2 and name in DEMO_FILES:
            return "final_demo_and_provenance"
        if parts[:2] == ("demo", "v2") and ((len(parts) == 3 and name in DEMO_V2_FILES) or (parts[2:3] == ("recordings",) and len(parts) == 4 and rel.suffix == ".json")):
            return "current_v2_demo_production_evidence"
        if parts[:2] == ("demo", "core_features") and ((len(parts) == 3 and name in DEMO_CORE_FILES) or (parts[2:3] == ("recordings",) and len(parts) == 4 and rel.suffix == ".json")):
            return "six_feature_demo_current_production_evidence"
        if rel.as_posix() in {"demo/v2/qa/subtitles.ass", "demo/v2/qa/final_frame_comparison.json"}:
            return "current_v2_demo_subtitle_source_or_frame_comparison"
    if parts[0] == "results":
        if parts[:2] == ("results", "core_features") and ((len(parts) == 3 and name in FEATURE_RESULT_FILES) or (len(parts) >= 4 and parts[2] in FEATURE_RESULT_DIRS and rel.suffix.lower() in {".json", ".csv", ".md", ".xml"})):
            return "independent_feature_demonstration_selftest_performance_or_acceptance"
        if parts[:3] == ("results", "core_features", "demo_runs") and name.endswith("_download.txt"):
            return "actual_simulated_export_download_evidence"
        if parts[:2] == ("results", "publication") and len(parts) == 3 and name in PUBLIC_SUMMARY_FILES:
            return "explicit_publication_summary"
        if parts[:3] == ("results", "launcher", "validation") and rel.suffix.lower() in {".json", ".md", ".xml"}:
            return "launcher_acceptance_evidence"
        for group in FORMAL_COUNTS:
            prefix = ("results", *Path(group).parts)
            if parts[:len(prefix)] == prefix:
                rest = parts[len(prefix):]
                if len(rest) == 1 and name in FORMAL_FILES:
                    return "formal_experiment_index_or_manifest"
                if len(rest) == 2 and rest[0] == "records" and rel.suffix == ".json":
                    return "formal_raw_record"
        if len(parts) == 3 and parts[1] == "environment" and name in ENVIRONMENT_FILES:
            return "environment_and_model_evidence"
        if len(parts) == 3 and parts[1] == "validation" and validation_report_name(name):
            return "acceptance_or_validation_report"
        if parts[:3] == ("results", "v2", "validation") and len(parts) == 4 and (validation_report_name(name) or rel.suffix.lower() == ".md"):
            return "v2_acceptance_or_validation_report"
        if parts[:4] == ("results", "v2", "launcher", "validation") and rel.suffix.lower() in {".json", ".md", ".xml"}:
            return "v2_launcher_acceptance_evidence"
        if parts[:3] == ("results", "v2", "browser") and ((len(parts) == 4 and name in BROWSER_FILES) or (parts[3:4] == ("video_timing",) and len(parts) == 5 and name in BROWSER_TIMING_FILES)):
            return "v2_browser_acceptance_evidence"
        if parts[:3] == ("results", "v2", "acceptance") and len(parts) == 5 and name in {"acceptance.json", "checks.json", "checks_actual_state.json"}:
            return "v2_actual_api_state_acceptance_summary"
        if rel.as_posix() == "results/comparison.json":
            return "formal_comparison"
        if rel.as_posix() in {"results/v2/comparison.json", "results/v2/frozen_manifest.json", "results/v2/demo_selection.json"}:
            return "v2_comparison_or_runtime_freeze"
    return None


def select_files(root: Path, profile: str = "light") -> tuple[list[Path], list[dict], dict[str, str]]:
    if profile not in {"light", "full"}:
        raise ValueError("Unknown package profile")
    root = root.resolve()
    public_manifest = root / "PUBLICATION_MANIFEST.json"
    public_allowlist = set(read_json(public_manifest).get("files", {})) | {"PUBLICATION_MANIFEST.json"} if public_manifest.exists() else None
    references = referenced_document_images(root) | referenced_evidence(root) if profile == "light" else set()
    selected, excluded, reasons = [], [], {}
    for base, dirs, names in os.walk(root, followlinks=False):
        for directory in list(dirs):
            full = Path(base) / directory
            rel = full.relative_to(root)
            skip = excluded_directory(directory) or full.is_symlink() or getattr(os.path, "isjunction", lambda _: False)(full)
            skip |= rel.as_posix() in {"docs/qa/tools", "demo/raw", "demo/pickups", "dist/package_verify", "dist/package_light_verify", "dist/history", "results/runtime"}
            # Only the two report files directly under dist are distribution
            # inputs. Do not traverse previous staging/extraction trees.
            skip |= rel.parts[:1] == ("dist",) and len(rel.parts) > 1
            skip |= rel.parts[:2] == ("results", "launcher") and len(rel.parts) >= 3 and rel.parts[2] != "validation"
            skip |= rel.parts[:3] == ("results", "v2", "launcher") and len(rel.parts) >= 4 and rel.parts[3] != "validation"
            if skip:
                dirs.remove(directory)
                excluded.append({"path": rel.as_posix() + "/", "reason": "runtime_tools_cache_raw_media_or_transient_state", "kind": "directory"})
        for name in names:
            path = Path(base) / name
            rel = path.relative_to(root)
            reason = "symlink" if path.is_symlink() else global_file_exclusion(rel)
            if reason is None and public_allowlist is not None and rel.as_posix() not in public_allowlist:
                reason = "outside_explicit_publication_allowlist"
            if reason is None and profile == "light" and rel.parts[:2] == ("docs", "assets") and rel.parts[2:3] in (("user-manual",), ("core-features",), ("development-delivery",)) and rel.parts[3:4] == ("captures",) and rel.name != "capture_manifest.json":
                reason = "intermediate_manual_capture_pixels_or_debug_data"
            if reason is None and rel.parts[:2] == ("results", "core_features") and any(part.lower() in {"session", "sessions", "runtime", "raw", "logs", "recordings", "captures", "private", "checkpoints"} for part in rel.parts[2:-1]):
                reason = "active_or_intermediate_feature_demonstration_state"
            if reason is None and rel.parts[:3] == ("results", "core_features", "performance") and rel.name in {"measurement.json", "process_memory.jsonl", "gpu_device.jsonl"}:
                reason = "raw_process_measurement_represented_by_public_summary"
            if reason is None and rel.parts[:2] == ("results", "launcher") and (rel.parts[:3] != ("results", "launcher", "validation") or rel.suffix.lower() not in {".json", ".md", ".xml"}):
                reason = "transient_launcher_state_or_log"
            if reason is None and rel.parts[:3] == ("results", "v2", "launcher") and (rel.parts[:4] != ("results", "v2", "launcher", "validation") or rel.suffix.lower() not in {".json", ".md", ".xml"}):
                reason = "transient_launcher_state_or_log"
            if reason is None and rel.parts[0] == "dist" and name not in {"project_report.docx", "project_report.pdf"}:
                reason = "previous_build_or_package_verification"
            if reason is None and profile == "full" and rel.parts[:3] == ("docs", "qa", "render") and path.suffix != ".png":
                reason = "duplicate_render_output"
            inclusion = light_reason(rel, references) if profile == "light" else "full_evidence_profile"
            if reason is None and inclusion is None:
                reason = "outside_light_semantic_allowlist"
            if reason:
                excluded.append({"path": rel.as_posix(), "reason": reason, "bytes": path.stat().st_size, "kind": "file"})
            else:
                selected.append(path)
                reasons[rel.as_posix()] = inclusion
    return sorted(selected), sorted(excluded, key=lambda item: item["path"]), reasons


def files(root: Path = ROOT, profile: str = "light"):
    yield from select_files(root, profile)[0]


def git_metadata(root: Path) -> dict:
    if not (root / ".git").exists():
        return {"git_commit": None, "git_status": "not_present_in_extracted_delivery", "git_dirty": None}
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True)
        changes = subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True, check=True)
        return {"git_commit": result.stdout.strip(), "git_status": "available", "git_dirty": bool(changes.stdout.strip())}
    except (OSError, subprocess.CalledProcessError):
        return {"git_commit": None, "git_status": "git_command_unavailable", "git_dirty": None}


def file_table(root: Path, paths: list[Path]) -> dict:
    return {p.relative_to(root).as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(paths)}


def frontend_paths(root: Path, kind: str) -> list[Path]:
    directory = root / "frontend"
    paths = []
    if kind == "source":
        paths += [directory / name for name in sorted(FRONTEND_FILES - {"build_manifest.json", ".gitignore"}) if (directory / name).is_file()]
        prefixes = [directory / "src", directory / "public"]
    else:
        prefixes = [directory / "dist"]
    for prefix in prefixes:
        if prefix.exists():
            paths += [p for p in prefix.rglob("*") if p.is_file() and not p.is_symlink() and not global_file_exclusion(p.relative_to(root))]
    return sorted(set(paths))


class AssetHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        fields = {"script": ("src",), "img": ("src",), "source": ("src",), "video": ("src", "poster"), "audio": ("src",), "iframe": ("src",)}.get(tag, ())
        if tag == "link" and any(x in attrs.get("rel", "").split() for x in ("stylesheet", "icon", "preload", "modulepreload")):
            fields = ("href",)
        self.references.extend(attrs[key] for key in fields if attrs.get(key))


def check_static_assets(root: Path, chosen: set[str] | None = None) -> dict:
    dist = (root / "frontend/dist").resolve()
    if not (dist / "index.html").is_file():
        raise ValueError("Missing frontend/dist/index.html; run the frontend production build")
    references = []
    for path in frontend_paths(root, "artifact"):
        text = path.read_text(encoding="utf-8") if path.suffix.lower() in {".html", ".css", ".js", ".mjs"} else ""
        values = []
        if path.suffix == ".html":
            parser = AssetHTML()
            parser.feed(text)
            values = parser.references
        elif path.suffix == ".css":
            values = re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", text)
            values += re.findall(r"@import\s+['\"]([^'\"]+)", text)
        elif path.suffix in {".js", ".mjs"}:
            values = re.findall(r"\b(?:from\s*|import\s*(?:\(\s*)?)[\"']([^\"']+)[\"']", text)
            values += re.findall(r"new\s+URL\(\s*['\"]([^'\"]+)['\"]\s*,\s*import\.meta\.url", text)
            values = [v for v in values if v.startswith((".", "/"))]
        for value in values:
            url = urlsplit(value)
            if not value or value.startswith("#") or url.scheme in {"data", "blob"}:
                continue
            if url.scheme or url.netloc:
                raise ValueError("Remote auto-loaded frontend asset violates offline delivery: " + value)
            clean = unquote(url.path)
            target = (dist / clean.lstrip("/")) if clean.startswith("/") else path.parent / clean
            target = target.resolve()
            if not target.is_relative_to(dist) or not target.is_file():
                raise ValueError("Missing or escaping frontend asset: " + value)
            rel = target.relative_to(root.resolve()).as_posix()
            if chosen is not None and rel not in chosen:
                raise ValueError("Referenced frontend asset was excluded: " + rel)
            references.append({"source": path.relative_to(root).as_posix(), "reference": value, "target": rel, "sha256": sha(target)})
    return {"passed": True, "references": references, "external_auto_loaded_resources": []}


def prepare_frontend(root: Path, npm: str | None = None) -> dict:
    """Run the real local production compiler, then bind source and asset hashes."""
    executable = npm or shutil.which("npm.cmd") or shutil.which("npm")
    if not executable:
        raise ValueError("npm is unavailable; install Node.js or pass --npm with its path")
    before_sources = file_table(root, frontend_paths(root, "source"))
    command = [executable, "run", "build"]
    result = subprocess.run(command, cwd=root / "frontend", capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
    if result.returncode:
        raise ValueError("Frontend build failed: " + (result.stdout + result.stderr)[-4000:])
    sources = file_table(root, frontend_paths(root, "source"))
    if sources != before_sources:
        raise ValueError("Frontend sources changed during compilation; rebuild after edits finish")
    artifacts = file_table(root, frontend_paths(root, "artifact"))
    manifest = {"schema_version": 1, "built_at_utc": datetime.now(timezone.utc).isoformat(), "build_command": ["npm", "run", "build"], "build_returncode": result.returncode, "source_files": sources, "artifact_files": artifacts, "source_fingerprint": hashlib.sha256(json.dumps(sources, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "static_assets": check_static_assets(root)}
    target = root / "frontend/build_manifest.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"frontend_build_manifest": str(target), "source_files": len(sources), "artifact_files": len(artifacts), "build_returncode": 0}


def validate_frontend(root: Path, chosen: set[str]) -> dict:
    manifest = read_json(root / "frontend/build_manifest.json")
    if manifest.get("build_returncode") != 0:
        raise ValueError("Frontend build manifest does not record a successful compiler run")
    for kind, field in (("source", "source_files"), ("artifact", "artifact_files")):
        actual = file_table(root, frontend_paths(root, kind))
        if not actual or actual != manifest.get(field):
            raise ValueError("Stale frontend build manifest: " + field)
        if not set(actual) <= chosen:
            raise ValueError("Frontend build inputs or outputs missing from the delivery")
    fingerprint = hashlib.sha256(json.dumps(manifest["source_files"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if manifest.get("source_fingerprint") != fingerprint:
        raise ValueError("Frontend source fingerprint mismatch")
    clean = read_json(root / "frontend/qa/clean_install_validation.json")
    if clean.get("install_exit_code") != 0 or not clean.get("all_assets_identical") or clean.get("tests_passed", 0) < 1 or clean.get("package_lock_sha256") != sha(root / "frontend/package-lock.json"):
        raise ValueError("Frontend clean installation validation is incomplete or stale")
    for item in clean.get("assets", []):
        target = (root / "frontend/dist" / item["path"].replace("\\", "/")).resolve()
        if not target.is_relative_to((root / "frontend/dist").resolve()) or not target.is_file() or sha(target) != item["sha256"] or not item.get("match"):
            raise ValueError("Frontend clean-build asset is stale or unsafe")
    if len(clean.get("assets", [])) != len(manifest["artifact_files"]):
        raise ValueError("Frontend clean-build artifact coverage differs")
    clean_tests = read_json(root / "frontend/qa/clean_install_tests.json")
    unit_tests = read_json(root / "frontend/qa/unit_tests.json")
    if clean_tests.get("numPassedTests") != clean["tests_passed"] or any(not report.get("success") or report.get("numFailedTests") != 0 for report in (clean_tests, unit_tests)):
        raise ValueError("Frontend test reports do not match the clean-install acceptance")
    return check_static_assets(root, chosen)


def current_source_manifest(root: Path, selected: list[Path]) -> dict:
    frontend_sources = set(frontend_paths(root, "source"))
    sources = [p for p in selected if p.relative_to(root).parts[0] in {"src", "scripts", "tests", "configs"} or p.relative_to(root).parts[:2] == ("frontend", "scripts") or p in frontend_sources or p.relative_to(root).as_posix() in {"pyproject.toml", "requirements.lock.txt", "启动项目.cmd", "关闭项目.cmd"}]
    table = file_table(root, sources)
    return {"files": table, "fingerprint": hashlib.sha256(json.dumps(table, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "meaning": "Hashes of the current delivered source/configuration/tests and frontend build inputs; not the historical v1 runtime hash."}


def backup_previous_light(root: Path, paths: dict[str, Path]) -> dict | None:
    if not paths["archive"].exists():
        return None
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + sha(paths["archive"])[:12]
    destination = root / "dist/history/light" / identifier
    destination.mkdir(parents=True, exist_ok=False)
    saved = {}
    for role, source in paths.items():
        if source.exists():
            target = destination / source.name
            before = sha(source)
            shutil.copy2(source, target)
            if sha(target) != before or sha(source) != before:
                raise ValueError("Existing delivery changed while creating backup")
            saved[role] = {"path": target.relative_to(root).as_posix(), "sha256": before, "bytes": target.stat().st_size}
    receipt = {"kind": "previous_light_delivery_preserved", "files": saved}
    (destination / "backup_manifest.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def required_files(profile: str) -> list[str]:
    paths = ["README.md", "requirements.lock.txt", "pyproject.toml", "data/test.jsonl", "data/dev.jsonl", "data/frozen_manifest.json", "results/main/summary.json", "results/ablation/summary.json", "demo/demo.mp4", "demo/demo_subtitles.srt", "demo/demo_script.md", "demo/video_validation.json", "demo/playback_validation.json", "demo/narration.json", "dist/project_report.docx", "dist/project_report.pdf", "docs/project_report.md", "configs/members.json", "docs/DELIVERY.md"]
    paths += ["demo/v2/" + name for name in DEMO_V2_FILES]
    paths += [f"docs/{prefix}/{name}" for prefix in ("qa", "v2/qa") for name in DOC_CURRENT_MIRRORS]
    paths += ["results/v2/demo_selection.json", "results/v2/browser/ui_acceptance.json", "results/v2/browser/model-offline-lifecycle.json", "results/v2/browser/model-offline-visual-review.json", "results/v2/browser/model-offline.json", "results/v2/browser/model-restored.json"]
    paths += ["results/v2/browser/video_timing/" + name for name in BROWSER_TIMING_FILES]
    if profile == "light":
        paths += ["启动项目.cmd", "关闭项目.cmd", "docs/LIGHT_PACKAGE.md", "demo/selected_evidence.json", "results/demo/records/development_recovery.json", "results/development_v3/records/18f1f34fcc3ae112629d286a.json", "results/development_v3/experiment_manifest.json"]
    paths += ["frontend/package.json", "frontend/package-lock.json", "frontend/build_manifest.json", "frontend/src/main.tsx", "frontend/dist/index.html", "src/taintlab/web/app.py", "configs/experiment_v2.lock.json", "data/v2/test.jsonl", "data/v2/dev.jsonl", "data/v2/frozen_manifest.json", "data/v2/selection_rules.json", "data/v2/upstream/source_payloads.json", "data/v2/upstream/BIPIA_LICENSE.txt", "data/v2/upstream/InjecAgent_LICENCE.txt", "docs/v2/DATA_SOURCES.md", "results/v2/validation/experiment_integrity.json"]
    paths += ["frontend/qa/" + name for name in FRONTEND_QA_FILES]
    paths += ["results/v2/launcher/validation/actual_windows_validation.json"]
    paths += ["docs/" + name for name in MANUAL_FILES]
    paths += ["docs/publication/manual_qa/manual_validation.json", "docs/publication/PUBLICATION_POLICY.md"]
    paths += [f"docs/{stem}.{suffix}" for stem in FEATURE_DOCUMENTS for suffix in ("md", "pdf", "docx")]
    paths += [f"docs/{folder}/{name}" for folder, _ in FEATURE_DOCUMENTS.values() for name in ("validation.json", "visual_review.json")]
    paths += ["docs/FEATURE_EVIDENCE_MATRIX.md", "data/demo/core_features/scenarios.json", "data/demo/core_features/external_handover.txt", "results/core_features/baseline_integrity.json", "results/core_features/formal_summary.json"]
    paths += ["results/core_features/" + name for name in ("canary_selftest.json", "performance_summary.json", "process_memory_public.jsonl")]
    paths += ["demo/core_features/" + name for name in ("selection.json", "edit_decisions.json", "composition_manifest.json", "narration_synthesis.json", "visual_review.json", "source_inventory.json", "recording_timing.json")]
    paths += [f"results/{group}/{name}" for group in FORMAL_COUNTS for name in FORMAL_FILES]
    return sorted(set(paths))


def validate_manual(root: Path, chosen: set[str], expected_version: str) -> dict:
    report = read_json(root / "docs/publication/manual_qa/manual_validation.json")
    if report.get("project_version") != expected_version or report.get("all_passed") is not True or not report.get("visual_review") or report.get("visual_review") in {"pending", "required_after_latest_render"}:
        raise ValueError("Current user manual review is incomplete or has a different version")
    if not isinstance(report.get("pages"), int) or report["pages"] < 1:
        raise ValueError("Current user manual page count is invalid")
    for suffix, field in (("md", "source_markdown_sha256"), ("docx", "docx_sha256"), ("pdf", "pdf_sha256")):
        name = "docs/USER_MANUAL." + suffix
        if name not in chosen or report.get(field) != sha(root / name):
            raise ValueError("Current user manual artifact is missing or stale: " + name)
    for name, expected in report.get("assets", {}).items():
        rel = local_reference(root, name)
        if rel is None or rel.parts[:3] != ("docs", "assets", "user-manual") or rel.as_posix() not in chosen or sha(root / rel) != expected:
            raise ValueError("Current user manual image/configuration is missing or stale")
    return {"passed": True, "pages": report["pages"], "artifacts": {suffix: report[field] for suffix, field in (("md", "source_markdown_sha256"), ("docx", "docx_sha256"), ("pdf", "pdf_sha256"))}, "asset_count": len(report.get("assets", {}))}


def validate_feature_documents(root: Path, chosen: set[str], expected_version: str) -> dict:
    checked = {}
    for stem, (folder, titles) in FEATURE_DOCUMENTS.items():
        report = read_json(root / "docs" / folder / "validation.json")
        if report.get("runtime_version") != expected_version or not report.get("release_version") or report.get("all_passed") is not True or report.get("visual_review") != "passed":
            raise ValueError("Six-chapter document QA is incomplete or version metadata is invalid: " + stem)
        if not isinstance(report.get("pages"), int) or report["pages"] < 1:
            raise ValueError("Six-chapter document page count is invalid: " + stem)
        artifacts = report.get("artifact_sha256", {})
        expected_names = {f"docs/{stem}.{suffix}" for suffix in ("md", "pdf", "docx")}
        if set(artifacts) != expected_names:
            raise ValueError("Six-chapter document QA must bind exactly its three actual formats: " + stem)
        for name, expected in {**artifacts, **report.get("assets", {})}.items():
            rel = local_reference(root, name)
            if rel is None or rel.as_posix() not in chosen or sha(root / rel) != expected:
                raise ValueError("Six-chapter document artifact or asset is missing or stale: " + name)
        review_name = f"docs/{folder}/visual_review.json"
        if review_name not in chosen or report.get("review_sha256") != sha(root / review_name):
            raise ValueError("Six-chapter document visual review binding is stale: " + stem)
        if read_json(root / review_name).get("all_passed") is not True:
            raise ValueError("Six-chapter document visual review has not passed: " + stem)
        headings = re.findall(r"^##\s+(.+?)\s*$", (root / f"docs/{stem}.md").read_text(encoding="utf-8-sig"), re.M)
        if len(headings) != 6 or any(title not in heading for title, heading in zip(titles, headings)):
            raise ValueError("Six-chapter document needs the six required main headings in order: " + stem)
        checked[stem] = {"passed": True, "pages": report["pages"], "chapters": headings, "artifacts": artifacts, "assets_checked": len(report.get("assets", {})), "release_version": report["release_version"]}
    return checked


def validate_preserved_feature_baseline(root: Path, chosen: set[str]) -> dict:
    report = read_json(root / "results/core_features/baseline_integrity.json")
    hashes = report.get("files", {})
    expected_records = {name for name in chosen if any(name.startswith(f"results/{group}/records/") and name.endswith(".json") for group in FORMAL_COUNTS)}
    if report.get("formal_records") != sum(FORMAL_COUNTS.values()) or not expected_records <= set(hashes):
        raise ValueError("Feature baseline does not bind every preserved formal record")
    for name, expected in hashes.items():
        rel = local_reference(root, name)
        if rel is None or rel.as_posix() not in chosen or sha(root / rel) != expected:
            raise ValueError("Preserved formal/runtime bytes changed: " + name)
    return {"passed": True, "formal_records": len(expected_records), "bound_files": len(hashes), "scope": "Compared with the saved start-of-update baseline; not a rerun of formal experiments."}


def validate_feature_measurement(root: Path) -> dict:
    report = read_json(root / "results/core_features/performance_summary.json")
    samples_path = root / "results/core_features/process_memory_public.jsonl"
    if report.get("formal_experiment") is not False or report.get("included_in_ASR") is not False or report.get("public_samples_sha256") != sha(samples_path):
        raise ValueError("Feature performance evidence is not clearly separated or its public samples are stale")
    samples = [json.loads(line) for line in samples_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    allowed = {"seconds_from_start", "phase", "role", "working_set_bytes", "private_commit_bytes"}
    if not samples or any(set(sample) != allowed for sample in samples) or report.get("projection", {}).get("rows") != len(samples):
        raise ValueError("Public process memory rows contain private/unexpected fields or count mismatch")
    canary = read_json(root / "results/core_features/canary_selftest.json")
    cases = canary.get("cases", [])
    if canary.get("all_passed") is not True or canary.get("formal_experiment") is not False or canary.get("included_in_ASR") is not False or canary.get("model_called") is not False:
        raise ValueError("Canary mechanism self-test is incomplete or confused with formal model evidence")
    if not cases or not {True, False} <= {case.get("expected_found") for case in cases} or any(case.get("matches_synthetic_expectation") is not True or case.get("expected_found") != case.get("detector_result", {}).get("found") for case in cases):
        raise ValueError("Canary mechanism positive/negative results do not match their declared synthetic controls")
    detector = root / "src/taintlab/evaluation/canary.py"
    if canary.get("detector", {}).get("source_sha256") != sha(detector):
        raise ValueError("Canary self-test detector source hash is stale")
    return {"passed": True, "memory_rows": len(samples), "canary_controls": len(cases), "formal_experiment": False, "scope": "Checks saved public measurement/self-test bindings; no new model inference."}


def validate_delivery(root: Path, profile: str, selected: list[Path]) -> dict[str, int]:
    chosen = {path.relative_to(root).as_posix() for path in selected}
    missing = [path for path in required_files(profile) if path not in chosen]
    if missing:
        raise ValueError("Missing required deliverables: " + ", ".join(missing))
    video, playback, document = (read_json(root / path) for path in ("demo/video_validation.json", "demo/playback_validation.json", "docs/qa/document_validation.json"))
    project_version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if any(report.get("project_version") != project_version for report in (video, playback, document)):
        raise ValueError("Current report/video validation must identify project_version " + project_version)
    if not video.get("valid") or not playback.get("all_passed"):
        raise ValueError("Media validation has not passed")
    if video["video_sha256"] != playback["video_sha256"] or video["video_sha256"] != sha(root / "demo/demo.mp4"):
        raise ValueError("Media validation is stale")
    if video.get("srt_sha256") != sha(root / "demo/demo_subtitles.srt"):
        raise ValueError("Subtitle validation is stale")
    if document["docx_sha256"] != sha(root / "dist/project_report.docx") or document["pdf_sha256"] != sha(root / "dist/project_report.pdf"):
        raise ValueError("Document validation is stale")
    if not document.get("visual_review") or document["visual_review"] == "required_after_latest_render":
        raise ValueError("Final document visual review is incomplete")
    if document.get("source_markdown_sha256") != sha(root / "docs/project_report.md"):
        raise ValueError("Document Markdown validation is stale")
    validate_production_evidence(root, chosen, project_version)
    validate_manual(root, chosen, project_version)
    validate_feature_documents(root, chosen, project_version)
    validate_preserved_feature_baseline(root, chosen)
    validate_feature_measurement(root)
    validate_browser_evidence(root, chosen, project_version)
    validate_frontend(root, chosen)
    for parent in (Path("data"), Path("data/v2")):
        frozen = read_json(root / parent / "frozen_manifest.json")
        if not frozen.get("frozen"):
            raise ValueError("Dataset is not frozen: " + str(parent))
        for name, expected_hash in frozen["files"].items():
            relative = parent / name
            if relative.as_posix() not in chosen or sha(root / relative) != expected_hash:
                raise ValueError("Frozen data/source/license mismatch: " + relative.as_posix())
    counts = {}
    for group, expected in FORMAL_COUNTS.items():
        prefix = f"results/{group}/records/"
        records = {Path(path).stem for path in chosen if path.startswith(prefix) and path.endswith(".json")}
        manifest = read_json(root / f"results/{group}/experiment_manifest.json")
        rows = [json.loads(line) for line in (root / f"results/{group}/metrics.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(records) != expected or manifest["planned_runs"] != expected or len(rows) != expected or {row["run_id"] for row in rows} != records:
            raise ValueError(f"Incomplete formal evidence for {group}: expected {expected} paired index/record entries")
        if read_json(root / f"results/{group}/summary.json").get("total_runs") != expected:
            raise ValueError("Formal summary count mismatch: " + group)
        for identifier in records:
            record = read_json(root / f"results/{group}/records/{identifier}.json")
            if record.get("run_id") != identifier or record.get("backend_type") not in FORMAL_BACKEND_TYPES:
                raise ValueError("Formal record identity/backend mismatch: " + group + "/" + identifier)
        counts[group] = len(records)
    recovery = read_json(root / "results/demo/records/development_recovery.json")
    source = local_reference(root, recovery["source_record_path"])
    if source is None or source.as_posix() not in chosen or sha(root / source) != recovery["source_record_sha256"] or "development_v3" not in recovery.get("evidence_note", ""):
        raise ValueError("The old-version recovery trace, original source or version label is missing/stale")
    validate_demo_evidence(root, chosen, project_version)
    integrity = read_json(root / "results/v2/validation/experiment_integrity.json")
    if not integrity.get("all_passed"):
        raise ValueError("Current v2 independent experiment integrity validation has not passed")
    return counts


def grouped_sizes(root: Path, selected: list[Path]) -> dict:
    groups = defaultdict(lambda: {"files": 0, "bytes": 0})
    for path in selected:
        rel = path.relative_to(root)
        label = "/".join(rel.parts[:2]) if rel.parts[0] in {"results", "demo", "docs"} else rel.parts[0]
        groups[label]["files"] += 1
        groups[label]["bytes"] += path.stat().st_size
    return dict(sorted(groups.items()))


def write_verified_archive(root: Path, selected: list[Path], manifest: dict, output: Path) -> dict:
    if manifest.get("profile") == "full" and output.exists():
        raise ValueError("Full evidence archives are immutable; preserve the existing archive and choose a new version")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    checks = manifest["files"]
    payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in selected:
                archive.write(path, f"{ARCHIVE_ROOT}/{path.relative_to(root).as_posix()}")
            archive.writestr(f"{ARCHIVE_ROOT}/DELIVERY_MANIFEST.json", payload)
            archive.writestr(f"{ARCHIVE_ROOT}/PACKAGE_SHA256SUMS.txt", "".join(f"{meta['sha256']}  {name}\n" for name, meta in checks.items()))
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None or len(archive.infolist()) != len(checks) + 2:
                raise ValueError("Archive CRC/count validation failed")
            for name, meta in checks.items():
                if hashlib.sha256(archive.read(f"{ARCHIVE_ROOT}/{name}")).hexdigest() != meta["sha256"]:
                    raise ValueError("Source changed during packaging: " + name)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"path": output.relative_to(root).as_posix(), "sha256": sha(output), "bytes": output.stat().st_size, "verified_entries": len(checks) + 2}


def build(root: Path = ROOT, profile: str = "light", preview: bool = False) -> dict:
    root = root.resolve()
    selected, excluded, reasons = select_files(root, profile)
    paths = output_paths(root, profile)
    chosen = {path.relative_to(root).as_posix() for path in selected}
    if preview:
        return {"profile": profile, "preview_only": True, "outputs": {key: value.relative_to(root).as_posix() for key, value in paths.items()}, "selected_files": len(selected), "selected_bytes": sum(path.stat().st_size for path in selected), "groups": grouped_sizes(root, selected), "excluded_by_reason": dict(Counter(item["reason"] for item in excluded)), "missing_required_files": [p for p in required_files(profile) if p not in chosen]}
    counts = validate_delivery(root, profile, selected)
    checks = {path.relative_to(root).as_posix(): {"sha256": sha(path), "bytes": path.stat().st_size} for path in selected}
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    manifest = {
        "schema_version": 3, "builder_version": BUILDER_VERSION, "profile": profile,
        "project_version": project["version"], "created_at": datetime.now(timezone.utc).isoformat(), **git_metadata(root),
        "release_version": read_json(root / "docs/core_features_qa/validation.json")["release_version"],
        "original_source_commit": read_json(root / "configs/publication.json").get("source_commit") if (root / "configs/publication.json").is_file() else None,
        "runtime_sha256": read_json(root / "results/v2/baseline/experiment_manifest.json")["runtime_sha256"] if "v2/baseline" in counts else read_json(root / "results/main/experiment_manifest.json")["runtime_sha256"],
        "campaign_runtime_hashes": {group: read_json(root / f"results/{group}/experiment_manifest.json")["runtime_sha256"] for group in counts},
        "current_source": current_source_manifest(root, selected), "frontend_static_validation": validate_frontend(root, chosen),
        "demo_evidence_validation": validate_demo_evidence(root, chosen, project["version"]),
        "production_evidence_validation": validate_production_evidence(root, chosen, project["version"]),
        "manual_evidence_validation": validate_manual(root, chosen, project["version"]),
        "feature_document_validation": validate_feature_documents(root, chosen, project["version"]),
        "preserved_formal_runtime_validation": validate_preserved_feature_baseline(root, chosen),
        "feature_measurement_validation": validate_feature_measurement(root),
        "browser_evidence_validation": validate_browser_evidence(root, chosen, project["version"]),
        "weights_included": False, "inference_binaries_included": False, "dependency_environment_included": False,
        "first_preparation_requires_network": True, "formal_record_counts": counts,
        "preparation": {
            "platform": "Windows; other platforms have not been fully validated", "python": "Python 3.12; requirements.lock.txt pins dependencies",
            "commands": ["powershell -ExecutionPolicy Bypass -File scripts/install.ps1", ".venv/Scripts/python.exe scripts/model_prepare.py", "启动项目.cmd"],
            "model_source_lock": "configs/model.lock.json",
            "offline_after_preparation": "Prepared weights, llama.cpp binaries and Python environment are required. Application-socket validation is not physical whole-machine network isolation.",
            "media_recreation": "Final MP4/SRT are included. Prepare FFmpeg and the documented isolated browser, regenerate narration and make new recordings; raw takes/WAVs/QA rasters are not bundled in light.",
            "repack_without_git": "python scripts/build_package.py; Git metadata is optional.",
        },
        "included": {"files": len(checks), "bytes": sum(meta["bytes"] for meta in checks.values()), "groups": grouped_sizes(root, selected), "selection_reasons": reasons},
        "excluded": {"rules": EXCLUSION_RULES, "entries": excluded}, "files": checks,
    }
    manifest["previous_light_backup"] = backup_previous_light(root, paths) if profile == "light" else None
    manifest["archive"] = write_verified_archive(root, selected, manifest, paths["archive"])
    paths["manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksum_paths = [paths["archive"], paths["manifest"], root / "dist/project_report.docx", root / "dist/project_report.pdf", root / "demo/demo.mp4", root / "demo/demo_subtitles.srt"]
    checksum_paths += [root / f"docs/{stem}.{suffix}" for stem in (*FEATURE_DOCUMENTS, "USER_MANUAL") for suffix in ("md", "pdf", "docx")]
    paths["sha256"].write_text("".join(sha(path) + "  " + path.relative_to(root).as_posix() + "\n" for path in checksum_paths), encoding="utf-8")
    return manifest["archive"] | {"profile": profile, "manifest": paths["manifest"].relative_to(root).as_posix(), "checksums": paths["sha256"].relative_to(root).as_posix(), "formal_record_counts": counts}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("light", "full"), default="light", help="Light preserves a backup before replacement; full creates a separate immutable v2 evidence archive.")
    parser.add_argument("--preview", action="store_true", help="Print selection/size summary without building or changing any archive.")
    parser.add_argument("--prepare-frontend", action="store_true", help="Run npm run build and bind frontend source/artifact hashes; does not build a delivery archive.")
    parser.add_argument("--npm", help="Optional local npm executable for --prepare-frontend")
    parser.add_argument("--public", action="store_true", help="In the source checkout prepare a public snapshot; in an existing public snapshot verify Git tracking and build light. Does not initialize or push Git.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.public:
            if args.profile != "light" or args.prepare_frontend:
                raise ValueError("--public is the public light entrypoint; compile frontend separately first")
            from prepare_publication import plan, prepare, verify_tracking, verify_public_main
            if args.preview:
                payload, report = plan(ROOT, validate=False)
                result = {"public_preview_only": True, "files": len(payload), "formal_record_counts": report["formal_record_counts"], "credential_candidate_paths": sorted(report["credential_candidates"]), "missing_required_files": [p for p in required_files("light") if p not in payload]}
            elif (ROOT / "PUBLICATION_MANIFEST.json").is_file():
                binding = verify_public_main(ROOT) if (ROOT / ".git").exists() else {"status": "anonymous_source_archive_without_git", "main_commit_not_claimed": True}
                tracking = verify_tracking(ROOT) if (ROOT / ".git").exists() else {"status": "anonymous_source_archive_without_git", "tracking_not_claimed": True}
                result = build(ROOT, "light") | {"public_distribution": True, "git_tracking": tracking, "public_commit_binding": binding, "absolute_archive": str(ROOT / "dist/taintlab_project_light.zip")}
            else:
                destination = ROOT / "dist/publication" / ("public_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
                prepared = prepare(ROOT, destination)
                result = {"public_staging": prepared, "archive_built": False, "next_step": "Use prepare_publication.py --staging <snapshot> --sync-target <existing public branch> --sync-plan <plan.json>; review/apply it without new Git history, then commit, PR and squash-merge. Build --public only from the merged main commit. Source SHA metadata is not rewritten after the commit."}
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if args.prepare_frontend and args.preview:
            raise ValueError("--prepare-frontend changes compiled assets; it cannot be combined with --preview")
        print(json.dumps(prepare_frontend(ROOT, args.npm) if args.prepare_frontend else build(profile=args.profile, preview=args.preview), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
