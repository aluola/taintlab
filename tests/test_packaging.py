"""Meaningful delivery-selection and archive integrity regressions.

Fixture media/records below are explicitly synthetic and never experiment evidence.
"""
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest


SPEC = importlib.util.spec_from_file_location("taintlab_package_builder", Path(__file__).resolve().parents[1] / "scripts/build_package.py")
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


def put(root, relative, content="fixture"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def dump(root, relative, value):
    return put(root, relative, json.dumps(value, ensure_ascii=False))


def selected(root, profile="light"):
    return {path.relative_to(root).as_posix() for path in package.select_files(root, profile)[0]}


def test_default_light_has_separate_outputs_and_full_requires_explicit_profile(tmp_path):
    assert package.parse_args([]).profile == "light"
    assert package.parse_args(["--profile", "full"]).profile == "full"
    light, full = package.output_paths(tmp_path, "light"), package.output_paths(tmp_path, "full")
    assert light["archive"].name == "taintlab_project_light.zip"
    assert full["archive"].name == "taintlab_project_full_v2.zip"
    assert set(light.values()).isdisjoint(full.values())


def test_semantic_allowlist_retains_referenced_figures_but_omits_intermediates(tmp_path):
    keep = {"README.md", "AGENTS.md", "启动项目.cmd", "关闭项目.cmd", "scripts/start.py", "src/taintlab/app.py", "tests/test_example.py", "configs/model.lock.json", "configs/members.json", "requirements.lock.txt", "data/test.jsonl", "data/dev.jsonl", "data/frozen_manifest.json", ".streamlit/config.toml", "dist/project_report.pdf", "dist/project_report.docx", "demo/demo.mp4", "demo/demo_subtitles.srt", "demo/qa/visual_review.md", "docs/qa/figures/chart.png", "docs/qa/ui.png", "results/main/records/a.json", "results/ablation/records/b.json", "members/workload.csv"}
    omit = {".env", "src/.env.local", ".streamlit/secrets.toml", "models/weights.gguf", "vendor/server.exe", ".venv/pyvenv.cfg", "src/taintlab/__pycache__/app.pyc", "demo/voice/segments/001.wav", "demo/voice/voice.wav", "demo/qa/frame_001.png", "docs/qa/render/page-1.png", "docs/qa/figures/unreferenced.png", "docs/qa/tools/renderer.exe", "results/development_final/records/old.json", "results/environment/model.pid", "results/launcher/state.json", "results/launcher/service.log", "results/launcher/nested/data.json", "results/launcher/validation/browser.png", "results/launcher/validation/output.log", "scripts/debug.log", "dist/taintlab_project.zip", "dist/delivery_manifest.json"}
    keep.remove("demo/qa/visual_review.md")
    omit |= {"results/main/checkpoints.sqlite", "demo/qa/visual_review.md"}
    for name in keep | omit:
        put(tmp_path, name)
    put(tmp_path, "docs/report.md", "![Chart](docs/qa/figures/chart.png)\n![UI](qa/ui.png)\n![External](https://example.org/image.png)")
    keep.add("docs/report.md")
    chosen = selected(tmp_path)
    assert keep <= chosen
    assert not omit & chosen
    # An image is kept because the document references it, not because it is small.
    assert package.referenced_document_images(tmp_path) == {Path("docs/qa/figures/chart.png"), Path("docs/qa/ui.png")}


def test_launcher_evidence_exception_keeps_new_status_but_no_runtime_state(tmp_path):
    keep = {"results/launcher/validation/actual_windows_validation.json", "results/launcher/validation/initial_status.json", "results/launcher/validation/acceptance.json", "results/launcher/validation/pytest_launcher.xml", "results/launcher/validation/review.md"}
    omit = {"results/launcher/launcher_state.json", "results/launcher/model.pid", "results/launcher/lockfile.lock", "results/launcher/validation/run.log", "results/launcher/validation/screenshot.png"}
    for name in keep | omit:
        put(tmp_path, name)
    for profile in ("light", "full"):
        assert keep <= selected(tmp_path, profile)
        assert not omit & selected(tmp_path, profile)


def test_recovery_retains_only_selected_original_and_version_metadata(tmp_path):
    original = "results/development_v3/records/original.json"
    dump(tmp_path, original, {"backend_type": "synthetic_test_fixture"})
    dump(tmp_path, "results/development_v3/records/unneeded.json", {})
    dump(tmp_path, "results/demo/records/development_recovery.json", {"source_record_path": original, "evidence_note": "development_v3"})
    dump(tmp_path, "demo/selected_evidence.json", {"recovery": {"path": "results/demo/records/development_recovery.json"}})
    dump(tmp_path, "results/development_v3/experiment_manifest.json", {})
    dump(tmp_path, "results/development_v3/summary.json", {})
    chosen = selected(tmp_path)
    assert original in chosen
    assert "results/demo/records/development_recovery.json" in chosen
    assert "results/development_v3/experiment_manifest.json" in chosen
    assert "results/development_v3/records/unneeded.json" not in chosen


def test_current_validation_retains_referenced_offline_trace_not_previous_duplicates(tmp_path):
    current = "results/validation/offline_current.json"
    old = "results/validation/offline_unused.json"
    dump(tmp_path, current, {})
    dump(tmp_path, old, {})
    dump(tmp_path, "results/validation/offline_validation.json", {"runs": [{"trace": current}]})
    dump(tmp_path, "results/validation/offline_validation_previous_123.json", {"runs": [{"trace": old}]})
    chosen = selected(tmp_path)
    assert current in chosen
    assert old not in chosen
    assert "results/validation/offline_validation_previous_123.json" not in chosen


def test_full_profile_keeps_original_evidence_categories(tmp_path):
    evidence = {"demo/voice/voice.wav", "demo/qa/frame.png", "docs/qa/render/page-1.png", "results/development_final/records/example.json"}
    for name in evidence:
        put(tmp_path, name)
    assert evidence <= selected(tmp_path, "full")
    assert not evidence & selected(tmp_path, "light")


def test_no_git_repository_never_requires_git_executable(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise AssertionError("Git must not be called for an extracted delivery")
    monkeypatch.setattr(package.subprocess, "run", unavailable)
    assert package.git_metadata(tmp_path) == {"git_commit": None, "git_status": "not_present_in_extracted_delivery", "git_dirty": None}


def test_missing_git_executable_does_not_fail_packaging_metadata(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    def unavailable(*args, **kwargs):
        raise FileNotFoundError("git unavailable")
    monkeypatch.setattr(package.subprocess, "run", unavailable)
    assert package.git_metadata(tmp_path)["git_status"] == "git_command_unavailable"


def test_complete_fixture_build_can_be_extracted_and_repacked_without_git(tmp_path, monkeypatch):
    # Small, explicitly synthetic fixture exercises the full builder without
    # substituting fake results for the real project's 1296 saved runs.
    monkeypatch.setattr(package, "FORMAL_COUNTS", {"main": 1, "ablation": 1})
    monkeypatch.setattr(package, "FORMAL_BACKEND_TYPES", {"synthetic_test_fixture"})
    for relative in package.required_files("light"):
        put(tmp_path, relative, "unit-test fixture only")
    put(tmp_path, "pyproject.toml", '[project]\nname="fixture"\nversion="0.0.0"\n')
    for group in ("main", "ablation"):
        dump(tmp_path, f"results/{group}/records/run_{group}.json", {"run_id": f"run_{group}", "backend_type": "synthetic_test_fixture"})
        dump(tmp_path, f"results/{group}/experiment_manifest.json", {"planned_runs": 1, "runtime_sha256": "synthetic_fixture"})
        put(tmp_path, f"results/{group}/metrics.jsonl", json.dumps({"run_id": f"run_{group}"}) + "\n")
        dump(tmp_path, f"results/{group}/summary.json", {"total_runs": 1})
    original = "results/development_v3/records/18f1f34fcc3ae112629d286a.json"
    dump(tmp_path, original, {"backend_type": "synthetic_test_fixture"})
    dump(tmp_path, "results/demo/records/development_recovery.json", {"source_record_path": original, "source_record_sha256": package.sha(tmp_path / original), "evidence_note": "development_v3 synthetic fixture"})
    dump(tmp_path, "demo/selected_evidence.json", {"recovery": {"path": "results/demo/records/development_recovery.json"}})
    for relative in ("demo/video_validation.json", "demo/playback_validation.json"):
        dump(tmp_path, relative, {"project_version": "0.0.0", "valid": True, "all_passed": True, "video_sha256": package.sha(tmp_path / "demo/demo.mp4"), "srt_sha256": package.sha(tmp_path / "demo/demo_subtitles.srt")})
    dump(tmp_path, "docs/qa/document_validation.json", {"project_version": "0.0.0", "docx_sha256": package.sha(tmp_path / "dist/project_report.docx"), "pdf_sha256": package.sha(tmp_path / "dist/project_report.pdf"), "source_markdown_sha256": package.sha(tmp_path / "docs/project_report.md"), "visual_review": "synthetic unit fixture"})
    for folder in ("data", "data/v2"):
        dump(tmp_path, folder + "/frozen_manifest.json", {"frozen": True, "files": {"test.jsonl": package.sha(tmp_path / folder / "test.jsonl"), "dev.jsonl": package.sha(tmp_path / folder / "dev.jsonl")}})
    dump(tmp_path, "results/v2/validation/experiment_integrity.json", {"all_passed": True, "scope": "synthetic unit fixture only"})
    make_frontend_fixture(tmp_path)
    make_production_fixture(tmp_path, "0.0.0")
    make_manual_fixture(tmp_path, "0.0.0")
    result = package.build(tmp_path)
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(tmp_path / result["path"]) as archive:
        archive.extractall(unpacked)
    destination = unpacked / package.ARCHIVE_ROOT
    assert not (destination / ".git").exists()
    again = package.build(destination)
    saved = package.read_json(destination / again["manifest"])
    assert saved["git_commit"] is None
    assert saved["formal_record_counts"] == {"main": 1, "ablation": 1}
    assert "DELIVERY_MANIFEST.json" not in saved["files"]
    assert "PACKAGE_SHA256SUMS.txt" not in saved["files"]


def test_light_archive_content_verified_and_existing_full_package_unchanged(tmp_path):
    source = put(tmp_path, "README.md", "unit test archive content")
    old_full = put(tmp_path, "dist/taintlab_project.zip", "existing complete evidence sentinel")
    original_hash = package.sha(old_full)
    manifest = {"profile": "light", "files": {"README.md": {"sha256": package.sha(source), "bytes": source.stat().st_size}}}
    result = package.write_verified_archive(tmp_path, [source], manifest, package.output_paths(tmp_path, "light")["archive"])
    with zipfile.ZipFile(tmp_path / result["path"]) as archive:
        assert archive.read("taintlab_project/README.md").decode() == "unit test archive content"
        assert json.loads(archive.read("taintlab_project/DELIVERY_MANIFEST.json"))["profile"] == "light"
        assert package.sha(source) in archive.read("taintlab_project/PACKAGE_SHA256SUMS.txt").decode()
        assert archive.testzip() is None
    assert package.sha(old_full) == original_hash


def test_changed_source_fails_before_replacing_previous_light_archive(tmp_path):
    source = put(tmp_path, "README.md", "before")
    manifest = {"files": {"README.md": {"sha256": package.sha(source), "bytes": source.stat().st_size}}}
    destination = put(tmp_path, "dist/taintlab_project_light.zip", "previous good archive")
    source.write_text("changed while preparing", encoding="utf-8")
    with pytest.raises(ValueError, match="Source changed"):
        package.write_verified_archive(tmp_path, [source], manifest, destination)
    assert destination.read_text() == "previous good archive"
    assert not destination.with_suffix(".zip.tmp").exists()


def test_current_project_light_retains_all_formal_records_and_current_report_images():
    root = Path(__file__).resolve().parents[1]
    if not (root / "results/main/records").exists():
        pytest.skip("Formal evidence is unavailable in this source-only checkout")
    chosen = selected(root)
    for group, count in {"main": 972, "ablation": 324, "v2/baseline": 1296, "v2/external": 1080}.items():
        assert sum(path.startswith(f"results/{group}/records/") and path.endswith(".json") for path in chosen) == count
        assert all(f"results/{group}/{name}" in chosen for name in package.FORMAL_FILES)
    assert {"docs/v2/qa/figures/baseline.png", "docs/v2/qa/figures/external.png", "results/v2/browser/laptop-home.png", "results/v2/browser/confirmation-pending.png", "results/v2/browser/focused-source-graph-v2.png"} <= chosen
    assert "results/development_v3/records/18f1f34fcc3ae112629d286a.json" in chosen


def make_frontend_fixture(root):
    put(root, "frontend/package.json", '{"scripts":{"build":"fixture only"}}')
    put(root, "frontend/package-lock.json", '{}')
    put(root, "frontend/src/main.tsx", 'export const fixture = true')
    put(root, "frontend/dist/index.html", '<script type="module" src="/assets/main.js"></script><link rel="stylesheet" href="/assets/main.css">')
    put(root, "frontend/dist/assets/main.js", 'import "./chunk.js";')
    put(root, "frontend/dist/assets/chunk.js", 'export const fixture = true;')
    put(root, "frontend/dist/assets/main.css", 'body{background:url("./pixel.svg")}')
    put(root, "frontend/dist/assets/pixel.svg", '<svg xmlns="http://www.w3.org/2000/svg"/>')
    source = package.file_table(root, package.frontend_paths(root, "source"))
    artifacts = package.file_table(root, package.frontend_paths(root, "artifact"))
    import hashlib
    dump(root, "frontend/build_manifest.json", {"build_returncode": 0, "source_files": source, "artifact_files": artifacts, "source_fingerprint": hashlib.sha256(json.dumps(source,sort_keys=True,separators=(",",":")).encode()).hexdigest(), "scope": "synthetic unit fixture; no real frontend build"})
    dump(root, "frontend/qa/clean_install_validation.json", {"install_exit_code": 0, "tests_passed": 1, "all_assets_identical": True, "package_lock_sha256": package.sha(root / "frontend/package-lock.json"), "assets": [{"path": str(Path(name).relative_to("frontend/dist")), "sha256": data["sha256"], "match": True} for name, data in artifacts.items()], "scope": "synthetic unit fixture only"})
    for name in ("clean_install_tests.json", "unit_tests.json"):
        dump(root, "frontend/qa/" + name, {"success": True, "numPassedTests": 1, "numFailedTests": 0, "scope": "synthetic unit fixture only"})


def test_v2_source_assets_licenses_and_all_campaign_records_are_selected(tmp_path):
    keep = {"frontend/src/main.tsx", "frontend/dist/index.html", "frontend/dist/assets/main.js", "frontend/package-lock.json", "frontend/package.json", "frontend/build_manifest.json", "data/v2/upstream/BIPIA_LICENSE.txt", "data/v2/upstream/InjecAgent_LICENCE.txt", "data/v2/frozen_manifest.json", "data/v2/history/old_manifest.json", "docs/v2/DATA_SOURCES.md", "src/taintlab/web/app.py", "results/v2/baseline/records/current.json", "results/v2/external/records/current.json", "results/v2/external/metrics.csv", "results/v2/validation/experiment_integrity.json", "results/v2/launcher/validation/status.json"}
    keep |= {"frontend/qa/clean_install_validation.json", "frontend/qa/clean_install_tests.json", "frontend/qa/unit_tests.json", "frontend/scripts/browser_check.cjs", "results/v2/browser/ui_e2e.json"}
    omit = {"frontend/node_modules/dependency/index.js", "frontend/tsconfig.tsbuildinfo", "results/web_private/owners.json", "results/web_private/sessions/record.json", "results/web_private/uploads/text.txt", "results/v2/web_private/cookies.json", "results/v2/baseline/checkpoints.sqlite", "results/v2/launcher/service.pid", "results/v2/launcher/state.json", "results/v2/launcher/validation/frame.png", "dist/history/light/old/manifest.json"}
    omit |= {"frontend/.validation-build/dist/index.html", "frontend/.validation-target.txt"}
    for name in keep | omit:
        put(tmp_path, name, "{}" if name.endswith(".json") else "fixture")
    for profile in ("light", "full"):
        chosen = selected(tmp_path, profile)
        assert keep <= chosen
        assert not omit & chosen


def test_static_assets_are_checked_recursively_and_stale_sources_are_rejected(tmp_path):
    make_frontend_fixture(tmp_path)
    result = package.validate_frontend(tmp_path, selected(tmp_path))
    assert len(result["references"]) == 4
    put(tmp_path, "frontend/src/main.tsx", 'export const changed = true')
    with pytest.raises(ValueError, match="Stale frontend"):
        package.validate_frontend(tmp_path, selected(tmp_path))
    (tmp_path / "frontend/dist/assets/chunk.js").unlink()
    with pytest.raises(ValueError, match="Missing or escaping"):
        package.check_static_assets(tmp_path)


def test_remote_or_escaping_frontend_asset_is_not_silently_included(tmp_path):
    make_frontend_fixture(tmp_path)
    put(tmp_path, "frontend/dist/index.html", '<script src="https://example.invalid/app.js"></script>')
    with pytest.raises(ValueError, match="Remote auto-loaded"):
        package.check_static_assets(tmp_path)
    put(tmp_path, "frontend/dist/index.html", '<script src="../../private.js"></script>')
    with pytest.raises(ValueError, match="Missing or escaping"):
        package.check_static_assets(tmp_path)


def test_current_demo_development_reference_is_retained_with_manifest_only(tmp_path):
    record = "results/v2/development_v1/records/chosen.json"
    dump(tmp_path, record, {"backend_type": "synthetic_test_fixture"})
    dump(tmp_path, "results/v2/development_v1/records/unused.json", {})
    dump(tmp_path, "results/v2/development_v1/experiment_manifest.json", {})
    dump(tmp_path, "demo/selected_evidence.json", {"demo": {"path": record}})
    chosen = selected(tmp_path)
    assert record in chosen
    assert "results/v2/development_v1/experiment_manifest.json" in chosen
    assert "results/v2/development_v1/records/unused.json" not in chosen


def test_previous_light_archive_and_companion_files_are_backed_up(tmp_path):
    paths = package.output_paths(tmp_path, "light")
    for name, path in paths.items():
        put(tmp_path, path.relative_to(tmp_path), "previous " + name)
    receipt = package.backup_previous_light(tmp_path, paths)
    for role, metadata in receipt["files"].items():
        assert (tmp_path / metadata["path"]).read_bytes() == paths[role].read_bytes()
        assert package.sha(paths[role]) == metadata["sha256"]
    assert not any(x.startswith("dist/history/") for x in selected(tmp_path))


def test_full_archive_cannot_overwrite_an_existing_version(tmp_path):
    path = put(tmp_path, "dist/taintlab_project_full_v2.zip", "preserve")
    with pytest.raises(ValueError, match="immutable"):
        package.write_verified_archive(tmp_path, [], {"profile": "full", "files": {}}, path)
    assert path.read_text() == "preserve"


def test_current_api_acceptance_keeps_summary_and_only_selected_demo_trace(tmp_path):
    prefix = "results/v2/acceptance/current/"
    for name in ("acceptance.json", "checks.json", "checks_actual_state.json", "selected.json", "unused.json"):
        dump(tmp_path, prefix + name, {"scope": "synthetic fixture"})
    dump(tmp_path, "demo/selected_evidence.json", {"current": {"path": prefix + "selected.json"}})
    chosen = selected(tmp_path)
    assert {prefix + name for name in ("acceptance.json", "checks.json", "checks_actual_state.json", "selected.json")} <= chosen
    assert prefix + "unused.json" not in chosen


def test_demo_records_array_recursively_keeps_current_live_sources_and_checks_hashes(tmp_path):
    names = ["results/v2/demo_live/records/query.json", "results/v2/demo_live/records/export.json"]
    items = []
    for name in names:
        path = dump(tmp_path, name, {"backend_type": "synthetic_test_fixture", "purpose": name})
        items.append({"path": name, "sha256": package.sha(path)})
    unused = "results/v2/demo_live/records/unused.json"
    dump(tmp_path, unused, {})
    dump(tmp_path, "demo/selected_evidence.json", {"project_version": "2.0.0", "records": [items[0], {"group": [items[1]]}], "notes": ["Not a record path"]})
    chosen = selected(tmp_path)
    assert set(names) <= chosen
    assert unused not in chosen
    assert package.validate_demo_evidence(tmp_path, chosen, "2.0.0")["checked_records"] == 2
    # The declared source digest must still bind the actual bytes after selection.
    dump(tmp_path, names[1], {"changed": True})
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        package.validate_demo_evidence(tmp_path, chosen, "2.0.0")


@pytest.mark.parametrize("records", [[], "not an array", [{"purpose": "missing source"}], [[[]]]])
def test_malformed_demo_array_cannot_silently_skip_validation(tmp_path, records):
    dump(tmp_path, "demo/selected_evidence.json", {"project_version": "2.0.0", "records": records})
    with pytest.raises(ValueError, match="Selected demo"):
        selected(tmp_path)


def test_current_demo_requires_hash_version_and_package_membership(tmp_path):
    name = "results/v2/demo_live/records/live.json"
    path = dump(tmp_path, name, {"backend_type": "synthetic_test_fixture"})
    index = {"project_version": "2.0.0", "records": [{"path": name}]}
    dump(tmp_path, "demo/selected_evidence.json", index)
    with pytest.raises(ValueError, match="valid SHA256"):
        package.validate_demo_evidence(tmp_path, {name}, "2.0.0")
    index["records"][0]["sha256"] = package.sha(path)
    dump(tmp_path, "demo/selected_evidence.json", index)
    with pytest.raises(ValueError, match="different project version"):
        package.validate_demo_evidence(tmp_path, {name}, "1.0.0")
    with pytest.raises(ValueError, match="missing or excluded"):
        package.validate_demo_evidence(tmp_path, set(), "2.0.0")


def test_demo_reference_cannot_override_private_state_exclusion(tmp_path):
    name = "results/web_private/records/private.json"
    path = dump(tmp_path, name, {"scope": "synthetic private fixture"})
    dump(tmp_path, "demo/selected_evidence.json", {"project_version": "2.0.0", "records": [{"path": name, "sha256": package.sha(path)}]})
    chosen = selected(tmp_path)
    assert name not in chosen
    with pytest.raises(ValueError, match="missing or excluded"):
        package.validate_demo_evidence(tmp_path, chosen, "2.0.0")


def make_production_fixture(root, version="2.0.0"):
    for name in ("demo/demo.mp4", "demo/narration.json", "demo/v2/demo_upload.md", "results/v2/demo_selection.json"):
        if not (root / name).exists():
            put(root, name, "synthetic unit fixture only")
    dump(root, "demo/v2/visual_review.json", {"project_version": version, "video_sha256": package.sha(root / "demo/demo.mp4"), "passed": True})
    dump(root, "demo/v2/edit_decisions.json", {"project_version": version, "scope": "synthetic unit fixture"})
    dump(root, "demo/v2/composition_manifest.json", {"project_version": version, "edl_sha256": package.sha(root / "demo/v2/edit_decisions.json")})
    dump(root, "demo/v2/narration_synthesis.json", {"narration_sha256": package.sha(root / "demo/narration.json")})
    dump(root, "demo/v2/recordings/fixture.json", {"version": version, "selection_file": "results/v2/demo_selection.json", "selection_sha256": package.sha(root / "results/v2/demo_selection.json"), "upload_file": "demo/v2/demo_upload.md", "upload_sha256": package.sha(root / "demo/v2/demo_upload.md")})
    for name in package.DOC_CURRENT_MIRRORS:
        source = root / "docs/qa" / name
        if not source.exists():
            put(root, source.relative_to(root), "synthetic unit fixture only")
        put(root, "docs/v2/qa/" + name, source.read_text(encoding="utf-8"))
    dump(root, "results/v2/browser/ui_acceptance.json", {"version": version, "all_targeted_checks_passed_latest_evidence": True, "browser_reports": []})


def make_manual_fixture(root, version="2.0.0"):
    for suffix in ("md", "pdf", "docx"):
        put(root, "docs/USER_MANUAL." + suffix, "synthetic unit manual fixture only")
    image = put(root, "docs/assets/user-manual/originals/example.png", "synthetic image fixture")
    value = {"project_version": version, "all_passed": True, "visual_review": "synthetic test fixture only", "pages": 1, "assets": {image.relative_to(root).as_posix(): package.sha(image)}}
    value.update({field: package.sha(root / ("docs/USER_MANUAL." + suffix)) for suffix, field in (("md", "source_markdown_sha256"), ("docx", "docx_sha256"), ("pdf", "pdf_sha256"))})
    dump(root, "docs/publication/manual_qa/manual_validation.json", value)


def test_user_manual_originals_annotations_configuration_and_qa_are_kept(tmp_path):
    keep = {"docs/USER_MANUAL.md", "docs/USER_MANUAL.pdf", "docs/USER_MANUAL.docx", "docs/assets/user-manual/originals/screen.png", "docs/assets/user-manual/annotated/screen.png", "docs/assets/user-manual/annotations.json", "docs/assets/user-manual/README.md", "docs/publication/manual_qa/manual_validation.json", "docs/publication/manual_qa/review.md", "results/publication/test_summary.json"}
    omit = {"docs/publication/manual_qa/render/page-1.png", "docs/publication/manual_qa/render.log", "results/publication/private_history_audit.json", "results/publication/public_git_pathspec.nul"}
    keep.add("docs/assets/user-manual/captures/example/capture_manifest.json")
    omit.add("docs/assets/user-manual/captures/example/duplicate.png")
    for name in keep | omit:
        put(tmp_path, name, "{}" if name.endswith(".json") else "fixture")
    chosen = selected(tmp_path)
    assert keep <= chosen
    assert not omit & chosen


@pytest.mark.parametrize("changed", ["docs/USER_MANUAL.pdf", "docs/assets/user-manual/originals/example.png"])
def test_manual_review_binds_actual_documents_and_source_images(tmp_path, changed):
    make_manual_fixture(tmp_path)
    chosen = selected(tmp_path)
    assert package.validate_manual(tmp_path, chosen, "2.0.0")["passed"]
    put(tmp_path, changed, "changed after review")
    with pytest.raises(ValueError, match="missing or stale"):
        package.validate_manual(tmp_path, chosen, "2.0.0")


def test_v2_media_and_browser_indices_keep_current_evidence_without_raw_duplicates(tmp_path):
    reports = [f"results/v2/browser/ui_followup_2026-10-26T17-{minute}-00-715Z.json" for minute in ("19", "33", "55")]
    keep = {"demo/v2/" + name for name in package.DEMO_V2_FILES}
    keep |= {"demo/v2/recordings/full_take.json", "demo/v2/qa/subtitles.ass", "demo/v2/qa/final_frame_comparison.json", "docs/v2/qa/visual_review_pages_1_12.json", "docs/v2/qa/document_validation.json", "docs/v2/qa/visual_review_page_hashes.json", "docs/v2/qa/structure_validation.json", "results/v2/browser/model-offline-lifecycle.json", "results/v2/browser/model-offline-visual-review.json", "results/v2/browser/video_timing/frame_alignment.json", "results/v2/browser/video_timing/timing_review.md", "results/v2/browser/ui_visual_review.md"}
    keep |= set(reports)
    omit = {"demo/v2/raw/take.webm", "demo/v2/intermediate/composed.mp4", "demo/v2/qa/frame.png", "demo/v2/qa/first_encode_visual_review.json", "demo/qa/visual_review.md", "demo/qa/subtitles.ass", "demo/voice/voice_manifest.json", "demo/voice/v2/voice.wav", "demo/patch_recording_metadata.json", "demo/recording_timing_second_take.json", "demo/composition_manifest.json", "results/v2/browser/video_timing/raw_120.png", "results/v2/browser/ui_followup_2026-10-26T01-00-00-000Z.json", "docs/v2/qa/render/page-1.png"}
    for name in keep | omit:
        put(tmp_path, name, "{}" if name.endswith(".json") else "synthetic fixture")
    dump(tmp_path, "results/v2/browser/ui_acceptance.json", {"version": "2.0.0", "all_targeted_checks_passed_latest_evidence": True, "browser_reports": [{"path": p, "sha256": package.sha(tmp_path / p)} for p in reports], "recording_timing_review": "results/v2/browser/video_timing/timing_review.md"})
    chosen = selected(tmp_path)
    assert keep <= chosen
    assert not omit & chosen
    assert len(package.validate_browser_evidence(tmp_path, chosen, "2.0.0")["reports"]) == 4
    (tmp_path / reports[0]).write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="report SHA256 mismatch"):
        package.validate_browser_evidence(tmp_path, chosen, "2.0.0")


@pytest.mark.parametrize("failure", ["video_changed", "review_failed", "qa_mirror_changed", "recording_source_changed"])
def test_current_production_evidence_cannot_be_satisfied_by_stale_media_or_reviews(tmp_path, failure):
    make_production_fixture(tmp_path)
    chosen = selected(tmp_path)
    assert package.validate_production_evidence(tmp_path, chosen, "2.0.0")["passed"]
    if failure == "video_changed":
        put(tmp_path, "demo/demo.mp4", "changed after actual review")
    elif failure == "review_failed":
        review = package.read_json(tmp_path / "demo/v2/visual_review.json")
        review["passed"] = False
        dump(tmp_path, "demo/v2/visual_review.json", review)
    elif failure == "qa_mirror_changed":
        put(tmp_path, "docs/v2/qa/document_validation.json", "stale mirror")
    else:
        put(tmp_path, "demo/v2/demo_upload.md", "changed recording input")
    with pytest.raises(ValueError):
        package.validate_production_evidence(tmp_path, chosen, "2.0.0")


def test_browser_index_cannot_point_to_missing_or_unapproved_evidence(tmp_path):
    dump(tmp_path, "results/v2/browser/ui_acceptance.json", {"version": "2.0.0", "all_targeted_checks_passed_latest_evidence": True, "browser_reports": [{"path": "results/v2/browser/ui_followup_2026-10-26T17-00-00-000Z.json", "sha256": "0" * 64}]})
    with pytest.raises(ValueError, match="reference missing or excluded"):
        package.validate_browser_evidence(tmp_path, selected(tmp_path), "2.0.0")
