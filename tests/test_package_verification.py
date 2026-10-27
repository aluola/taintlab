"""Archive verifier tests use tiny synthetic packages, never formal evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import zipfile

import pytest

SPEC = importlib.util.spec_from_file_location("taintlab_light_verifier", Path(__file__).resolve().parents[1] / "scripts/verify_light_package.py")
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def archive_fixture(path, content=b"fixture", expected=None, extra=None):
    digest = hashlib.sha256(content if expected is None else expected).hexdigest()
    manifest = {"profile": "light", "files": {"README.md": {"sha256": digest, "bytes": len(content)}}}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("taintlab_project/README.md", content)
        archive.writestr("taintlab_project/DELIVERY_MANIFEST.json", json.dumps(manifest))
        archive.writestr("taintlab_project/PACKAGE_SHA256SUMS.txt", f"{digest}  README.md\n")
        if extra:
            archive.writestr(*extra)


def test_extract_verifies_every_declared_file_and_retains_archive(tmp_path):
    archive = tmp_path / "light.zip"
    archive_fixture(archive)
    old = verify.sha(archive)
    root, manifest, files = verify.extract_and_verify(archive, tmp_path / "independent")
    assert root.name == "taintlab_project"
    assert manifest["profile"] == "light"
    assert files == [{"path": "README.md", "sha256": hashlib.sha256(b"fixture").hexdigest(), "bytes": 7, "passed": True}]
    assert verify.sha(archive) == old


@pytest.mark.parametrize("name", ["../outside.txt", "taintlab_project/../../outside.txt", "C:/outside.txt", "taintlab_project/back\\slash.txt", "taintlab_project/a.txt:stream"])
def test_rejects_unsafe_paths_before_extraction(tmp_path, name):
    archive = tmp_path / "bad.zip"
    archive_fixture(archive, extra=(name, b"bad"))
    destination = tmp_path / "new"
    with pytest.raises(ValueError):
        verify.extract_and_verify(archive, destination)
    assert not destination.exists()


def test_rejects_case_collisions_on_windows(tmp_path):
    archive = tmp_path / "bad.zip"
    archive_fixture(archive, extra=("taintlab_project/readme.md", b"other"))
    with pytest.raises(ValueError, match="Duplicate"):
        verify.extract_and_verify(archive, tmp_path / "new")


def test_rejects_symbolic_link_entries(tmp_path):
    archive = tmp_path / "bad.zip"
    info = zipfile.ZipInfo("taintlab_project/link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    archive_fixture(archive, extra=(info, b"../../outside"))
    with pytest.raises(ValueError, match="linked"):
        verify.extract_and_verify(archive, tmp_path / "new")


def test_rejects_undeclared_archive_file(tmp_path):
    archive = tmp_path / "bad.zip"
    archive_fixture(archive, extra=("taintlab_project/extra.txt", b"undeclared"))
    with pytest.raises(ValueError, match="entry list"):
        verify.extract_and_verify(archive, tmp_path / "new")


def test_hash_mismatch_is_not_reported_as_verified(tmp_path):
    archive = tmp_path / "bad.zip"
    archive_fixture(archive, expected=b"different content")
    with pytest.raises(ValueError, match="hash/size mismatch"):
        verify.extract_and_verify(archive, tmp_path / "new")


def test_existing_destination_is_never_overwritten(tmp_path):
    archive = tmp_path / "light.zip"
    archive_fixture(archive)
    destination = tmp_path / "already_exists"
    destination.mkdir()
    sentinel = destination / "user.txt"
    sentinel.write_text("preserve")
    with pytest.raises(ValueError, match="new independent directory"):
        verify.extract_and_verify(archive, destination)
    assert sentinel.read_text() == "preserve"


def test_verifier_defaults_do_not_install_or_start_services():
    options = verify.parse_args([])
    assert options.install == "none"
    assert not options.run_packaging_tests
    assert options.output.name == "light_package_validation.json"
    assert "dist" in options.output.parts


def test_readme_generated_output_is_distinct_from_missing_runtime_entry(tmp_path):
    names = ["启动项目.cmd", "关闭项目.cmd", "scripts/model_prepare.py", "scripts/project_lifecycle.py", "scripts/launch_model.py", "scripts/install.ps1", "configs/model.json", "configs/model.lock.json", "configs/launcher.json"]
    for name in names:
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('%~dp0' if name.endswith('.cmd') else '{}', encoding='utf-8')
    (tmp_path / 'configs/model.lock.json').write_text(json.dumps({'model_file':'models/model.gguf'}), encoding='utf-8')
    readme = tmp_path / 'README.md'
    readme.write_text('启动项目.cmd 关闭项目.cmd scripts/model_prepare.py --output data/reproduced', encoding='utf-8')
    lifecycle = tmp_path / 'scripts/project_lifecycle.py'
    lifecycle.write_text('os.environ.get("SystemRoot", r"C:\\Windows")', encoding='utf-8')
    assert verify.portable_paths(tmp_path, tmp_path)['expected_after_reproduction'] == ['data/reproduced']
    assert verify.portable_paths(tmp_path, tmp_path)['system_directory_fallbacks'][0]['default'] == 'C:/Windows'
    lifecycle.write_text('ROOT = Path(r"D:\\old_project")', encoding='utf-8')
    with pytest.raises(ValueError, match='absolute original-machine path'):
        verify.portable_paths(tmp_path, tmp_path)
    lifecycle.write_text('{}', encoding='utf-8')
    readme.write_text(readme.read_text(encoding='utf-8')+' scripts/missing.py', encoding='utf-8')
    with pytest.raises(ValueError, match='missing local paths'):
        verify.portable_paths(tmp_path, tmp_path)


@pytest.mark.parametrize("name", ["taintlab_project/results/web_private/owners.json", "taintlab_project/results/v2/web_private/uploads/document.txt", "taintlab_project/frontend/node_modules/react/index.js", "taintlab_project/results/v2/baseline/checkpoints.sqlite", "taintlab_project/results/launcher/model.pid"])
def test_private_state_is_rejected_even_before_manifest_membership_check(tmp_path, name):
    archive = tmp_path / "bad.zip"
    archive_fixture(archive, extra=(name, b"private fixture"))
    with pytest.raises(ValueError, match="Private/runtime"):
        verify.extract_and_verify(archive, tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_v2_complete_evidence_denominator_is_prespecified():
    assert verify.FORMAL_COUNTS == {"main": 972, "ablation": 324, "v2/baseline": 1296, "v2/external": 1080}
    assert sum(verify.FORMAL_COUNTS.values()) == 3672


def test_independent_current_source_manifest_checks_current_bytes(tmp_path):
    path = tmp_path / "src" / "app.py"
    path.parent.mkdir()
    path.write_text("fixture", encoding="utf-8")
    files = {"src/app.py": {"sha256": verify.sha(path), "bytes": path.stat().st_size}}
    source = {"files": files, "fingerprint": hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    manifest = {"files": files, "current_source": source}
    assert verify.verify_current_source(tmp_path, manifest)["passed"]
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="differs from delivered bytes"):
        verify.verify_current_source(tmp_path, manifest)


def test_frozen_data_validation_includes_source_licenses(tmp_path):
    for prefix in ("data", "data/v2"):
        folder = tmp_path / prefix
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "source_license.txt"
        target.write_text("license fixture", encoding="utf-8")
        (folder / "frozen_manifest.json").write_text(json.dumps({"frozen": True, "files": {"source_license.txt": verify.sha(target)}}), encoding="utf-8")
    assert verify.verify_frozen_data(tmp_path)["passed"]
    (tmp_path / "data/v2/source_license.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="source/data/license mismatch"):
        verify.verify_frozen_data(tmp_path)


def test_independent_frontend_verification_rejects_changed_assets(tmp_path):
    files = {"frontend/package.json": "{}", "frontend/package-lock.json": "{}", "frontend/src/main.tsx": "fixture", "frontend/dist/index.html": '<script src="/assets/main.js"></script>', "frontend/dist/assets/main.js": "fixture"}
    for name, value in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    source = {name: {"sha256": verify.sha(tmp_path / name), "bytes": (tmp_path / name).stat().st_size} for name in files if "/dist/" not in name}
    assets = {name: {"sha256": verify.sha(tmp_path / name), "bytes": (tmp_path / name).stat().st_size} for name in files if "/dist/" in name}
    manifest = {"build_returncode": 0, "source_files": source, "artifact_files": assets, "source_fingerprint": hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    (tmp_path / "frontend/build_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    qa = tmp_path / "frontend/qa"
    qa.mkdir()
    (qa / "clean_install_validation.json").write_text(json.dumps({"install_exit_code": 0, "all_assets_identical": True, "package_lock_sha256": verify.sha(tmp_path / "frontend/package-lock.json"), "tests_passed": 1}), encoding="utf-8")
    (qa / "clean_install_tests.json").write_text(json.dumps({"success": True, "numFailedTests": 0, "numPassedTests": 1}), encoding="utf-8")
    assert verify.verify_frontend(tmp_path)["references_checked"] == 1
    (tmp_path / "frontend/dist/assets/main.js").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify.verify_frontend(tmp_path)


def test_independent_verifier_checks_nested_demo_records_and_detects_mutation(tmp_path):
    records = []
    for name in ("query", "export"):
        path = tmp_path / f"results/v2/demo_live/records/{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"scope": "synthetic test fixture", "task": name}), encoding="utf-8")
        records.append({"path": path.relative_to(tmp_path).as_posix(), "sha256": verify.sha(path)})
    index = tmp_path / "demo/selected_evidence.json"
    index.parent.mkdir()
    index.write_text(json.dumps({"project_version": "2.0.0", "records": [records[0], {"group": [records[1]]}], "notes": ["Not evidence"]}), encoding="utf-8")
    result = verify.verify_demo_evidence(tmp_path)
    assert result["passed"] and result["checked_records"] == 2
    (tmp_path / records[1]["path"]).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        verify.verify_demo_evidence(tmp_path)


@pytest.mark.parametrize("failure", ["missing_hash", "missing_file", "private", "escape", "malformed"])
def test_independent_demo_evidence_rejects_incomplete_or_private_sources(tmp_path, failure):
    source = tmp_path / "results/v2/demo_live/records/live.json"
    if failure == "private":
        source = tmp_path / "results/web_private/records/live.json"
    if failure == "escape":
        source = tmp_path.parent / (tmp_path.name + "_outside.json")
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('{"scope":"synthetic fixture"}', encoding="utf-8")
    relative = source.relative_to(tmp_path).as_posix() if failure != "escape" else "../" + source.name
    item = {"path": relative, "sha256": verify.sha(source)}
    if failure == "missing_hash":
        item.pop("sha256")
    if failure == "missing_file":
        source.unlink()
    index = tmp_path / "demo/selected_evidence.json"
    index.parent.mkdir()
    index.write_text(json.dumps({"records": [item] if failure != "malformed" else [{"purpose": "no source"}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        verify.verify_demo_evidence(tmp_path)


@pytest.mark.parametrize("failure", ["video_changed", "index_target_changed", "index_target_missing"])
def test_independent_current_reviews_bind_final_video_and_browser_report_references(tmp_path, failure):
    def write(name, content):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path
    write("pyproject.toml", '[project]\nversion="2.0.0"\n')
    video = write("demo/demo.mp4", "synthetic media fixture only")
    write("demo/v2/visual_review.json", json.dumps({"project_version": "2.0.0", "video_sha256": verify.sha(video), "all_passed": True}))
    for name in ["document_validation.json", "structure_validation.json", "visual_review_page_hashes.json", "visual_review.md"]:
        for directory in ["docs/qa", "docs/v2/qa"]:
            write(directory + "/" + name, "synthetic saved review fixture")
    relative = "results/v2/browser/ui_followup_2026-10-26T18-05-16-679Z.json"
    source = write(relative, "{}")
    write("results/v2/browser/ui_acceptance.json", json.dumps({"version": "2.0.0", "all_targeted_checks_passed_latest_evidence": True, "browser_reports": [{"path": relative, "sha256": verify.sha(source)}]}))
    assert verify.verify_current_reviews(tmp_path)["passed"]
    if failure == "video_changed":
        video.write_text("different bytes", encoding="utf-8")
    elif failure == "index_target_changed":
        source.write_text('{"changed":true}', encoding="utf-8")
    else:
        source.unlink()
    with pytest.raises(ValueError):
        verify.verify_current_reviews(tmp_path)


def feature_fixture(root):
    spec = importlib.util.spec_from_file_location("synthetic_feature_artifacts", Path(__file__).with_name("test_packaging.py"))
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    helper.put(root, "pyproject.toml", '[project]\nversion="2.0.0"\n')
    helper.make_production_fixture(root)
    helper.dump(root, "demo/video_validation.json", {})
    helper.make_feature_fixture(root)
    return helper


@pytest.mark.parametrize("failure", ["changed_pdf", "chapter_removed", "review_failed"])
def test_independent_feature_docs_verify_real_hashes_chapters_and_review(tmp_path, failure):
    helper = feature_fixture(tmp_path)
    assert len(verify.verify_feature_documents(tmp_path)) == 2
    name = "docs/CORE_FEATURES_GUIDE.pdf"
    qa_name = "docs/core_features_qa/validation.json"
    qa = verify.read_json(tmp_path / qa_name)
    if failure == "changed_pdf":
        helper.put(tmp_path, name, "changed reviewed artifact")
    elif failure == "chapter_removed":
        name = "docs/CORE_FEATURES_GUIDE.md"
        helper.put(tmp_path, name, "# Synthetic document without its required chapters")
        qa["artifact_sha256"][name] = verify.sha(tmp_path / name)
    else:
        name = "docs/core_features_qa/visual_review.json"
        helper.dump(tmp_path, name, {"all_passed": False})
        qa["review_sha256"] = verify.sha(tmp_path / name)
    helper.dump(tmp_path, qa_name, qa)
    with pytest.raises(ValueError):
        verify.verify_feature_documents(tmp_path)


def test_independent_feature_media_accepts_270_seconds_but_requires_actual_result_evidence(tmp_path):
    helper = feature_fixture(tmp_path)
    result = verify.verify_current_reviews(tmp_path)
    assert result["feature_chapters"]["actual_duration"] == 270
    assert result["video_visual_review"] == "demo/core_features/visual_review.json"
    helper.put(tmp_path, "results/core_features/demo_runs/synthetic.json", '{"changed":true}')
    with pytest.raises(ValueError, match="evidence hash mismatch"):
        verify.verify_current_reviews(tmp_path)


@pytest.mark.parametrize("name", ["source_inventory.json", "recording_timing.json"])
def test_independent_feature_media_rejects_missing_reproduction_configuration(tmp_path, name):
    feature_fixture(tmp_path)
    assert verify.verify_feature_video(tmp_path)["passed"]
    (tmp_path / "demo/core_features" / name).unlink()
    with pytest.raises(ValueError, match="reproduction metadata is missing"):
        verify.verify_feature_video(tmp_path)


def test_independent_public_measurement_rejects_pid_even_if_summary_hash_is_rebound(tmp_path):
    helper = feature_fixture(tmp_path)
    assert verify.verify_feature_measurement(tmp_path)["canary_controls"] == 2
    name = "results/core_features/process_memory_public.jsonl"
    row = json.loads((tmp_path / name).read_text(encoding="utf-8")); row["pid"] = 123
    helper.put(tmp_path, name, json.dumps(row) + "\n")
    qa = verify.read_json(tmp_path / "results/core_features/performance_summary.json")
    qa["public_samples_sha256"] = verify.sha(tmp_path / name)
    helper.dump(tmp_path, "results/core_features/performance_summary.json", qa)
    with pytest.raises(ValueError, match="private fields"):
        verify.verify_feature_measurement(tmp_path)


@pytest.mark.parametrize("relative", ["results/core_features/performance/run/measurement.json", "results/core_features/demo_runs/sessions/current.json", "vendor/model/runtime.dll"])
def test_independent_archive_privacy_rejects_raw_feature_runtime_and_binaries(relative):
    with pytest.raises(ValueError):
        verify.enforce_light_privacy(verify.PurePosixPath("taintlab_project") / relative)
