"""Synthetic repositories/artifacts only; never alter the project Git history."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(name, folder="scripts"):
    spec = importlib.util.spec_from_file_location("fixture_" + name, ROOT / folder / (name + ".py"))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


audit = load("audit_publication")
publication = load("prepare_publication")


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE)


def test_audit_separates_simulated_canary_cookie_names_and_recording_filenames():
    value = b'COOKIE="taintlab_session"\nSIM_CANARY_1234567890\npage@0123456789abcdef.webm\n'
    found = audit.scan_content(value)
    assert found["nonsecret_cookie_name"] == 1
    assert found["simulated_canary"] == 1
    assert found["noncontact_browser_recording_filename"] == 1
    assert not any(key.startswith("credential_candidate:") for key in found)
    private = "# Personal Gmail instructions\nfixture@example.invalid\n\n# 项目维护与交付约定\n- Keep public evidence accurate.\n".encode("utf-8")
    public, kind = publication.project_file("AGENTS.md", private)
    assert kind == "project_maintenance_instructions_only"
    assert b"Gmail" not in public and b"fixture@example.invalid" not in public
    assert private.startswith(b"# Personal")


def test_history_audit_visits_renamed_blob_paths_without_printing_candidate_values(tmp_path):
    git(tmp_path, "init", "--quiet")
    git(tmp_path, "config", "user.name", "Synthetic Fixture")
    git(tmp_path, "config", "user.email", "fixture@example.invalid")
    # Construct a deliberately nonfunctional test token; no real credential.
    token = "ghp_" + "".join(chr(65 + i % 26) for i in range(36))
    source = tmp_path / "example.txt"; source.write_text(token, encoding="utf-8")
    git(tmp_path, "add", "example.txt"); git(tmp_path, "commit", "--quiet", "-m", "synthetic fixture")
    git(tmp_path, "mv", "example.txt", "renamed.txt"); git(tmp_path, "commit", "--quiet", "-m", "synthetic rename")
    before = git(tmp_path, "rev-parse", "HEAD")
    summary, private = audit.audit_history(tmp_path)
    assert summary["reachable_commits"] == 2
    assert summary["credential_candidates"] == 1
    assert private["blobs"][0]["paths"] == ["example.txt", "renamed.txt"]
    assert token not in json.dumps(summary) and token not in json.dumps(private)
    assert git(tmp_path, "rev-parse", "HEAD") == before


def test_private_machine_reports_are_replaced_by_explicit_minimal_public_summaries(tmp_path):
    raw = json.dumps({"version": "2.0.0", "all_passed": True, "checks": {"actually_checked": True}, "steps": [{"pid": 1234, "argv": ["private location"]}], "initial": {"credentials": "fixture-private"}}).encode()
    data, kind = publication.project_file("results/v2/launcher/validation/actual_windows_validation.json", raw)
    summary = json.loads(data)
    assert kind == "explicit_public_summary" and summary["publication_summary"]
    assert summary["original_evidence_sha256"] == publication.digest(raw)
    assert summary["checks"] == {"actually_checked": True}
    assert "steps" not in summary and "initial" not in summary
    assert b"fixture-private" not in data
    old = tmp_path / "results/v2/validation/pytest.xml"
    current = tmp_path / "results/publication/pytest.xml"
    for path, count in [(old, 10), (current, 20)]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'<testsuites><testsuite tests="{count}" failures="0" errors="0" skipped="0"/></testsuites>', encoding="utf-8")
    tests = publication.public_test_summary(tmp_path)
    assert tests["sources"][0]["source"] == "results/publication/pytest.xml"
    assert tests["sources"][0]["tests"] == 20
    release_tests=tmp_path/"results/core_features/validation/pytest_release.xml"
    release_tests.parent.mkdir(parents=True)
    release_tests.write_text('<testsuites><testsuite tests="30" failures="0" errors="0" skipped="0"/></testsuites>',encoding="utf-8")
    newest=publication.public_test_summary(tmp_path)["sources"][0]
    assert newest["source"]=="results/core_features/validation/pytest_release.xml" and newest["tests"]==30
    assert publication.public_value(r"D:\temporary\private\runtime") == "[local-machine path omitted in public summary]"
    video = tmp_path / "demo/demo.mp4"
    video.parent.mkdir(); video.write_bytes(b"synthetic video fixture")
    playback = tmp_path / "results/publication/video_playback.json"
    playback.write_text(json.dumps({"video_sha256": publication.digest(video.read_bytes()), "all_passed": True, "samples": [{"time": 1}, {"time": 2}], "metadata": {"duration": 240}, "private_path": "omitted"}), encoding="utf-8")
    summary = publication.public_acceptance_summary(tmp_path)["reports"]["video_playback.json"]
    assert summary["samples_count"] == 2 and summary["metadata"]["duration"] == 240
    assert "private_path" not in summary
    video.write_bytes(b"changed video")
    with pytest.raises(ValueError, match="playback report is stale"):
        publication.public_acceptance_summary(tmp_path)


def test_source_zip_readme_relative_links_are_checked_without_claiming_web_checks():
    payload = {"README.md": b"[Manual](docs/manual.pdf) ![Image](images/a.png#fragment) [Web](https://example.invalid/) [Folder](src/)", "docs/manual.pdf": b"fixture", "images/a.png": b"fixture", "src/a.py": b"fixture"}
    result = publication.readme_links(payload)
    assert result["all_passed"] and result["directory_links"] == ["src/"]
    payload.pop("docs/manual.pdf")
    assert publication.readme_links(payload)["missing_links"] == ["docs/manual.pdf"]


def test_public_feature_junit_retains_actual_counts_without_host_or_console_details():
    raw = b'<testsuites><testsuite name="pytest" tests="2" failures="1" errors="0" skipped="0" hostname="synthetic-private-host"><testcase name="normal" time="1"/><testcase name="failure" time="2"><failure message="synthetic-private-details"/></testcase><system-out>synthetic-private-output</system-out></testsuite></testsuites>'
    public, kind = publication.project_file("results/core_features/packaging_tests.xml", raw)
    assert kind == "explicit_public_junit_summary"
    assert b'synthetic-private-' not in public
    tree = publication.ET.fromstring(public)
    assert tree.attrib["original_evidence_sha256"] == publication.digest(raw)
    suite = tree.find("testsuite")
    assert suite.attrib["tests"] == "2" and suite.attrib["failures"] == "1"
    assert len(suite.findall("testcase")) == 2 and suite.find("testcase/failure") is not None


def minimal_delivery(root, monkeypatch):
    builder = publication.module("build_package")
    helper = load("test_packaging", "tests")
    monkeypatch.setattr(helper, "package", builder)
    monkeypatch.setattr(builder, "FORMAL_COUNTS", {"main": 1, "ablation": 1, "v2/baseline": 1, "v2/external": 1})
    monkeypatch.setattr(builder, "FORMAL_BACKEND_TYPES", {"synthetic_test_fixture"})
    for name in builder.required_files("light"):
        helper.put(root, name, "{}" if name.endswith(".json") else "synthetic publication fixture only")
    helper.put(root, "pyproject.toml", '[project]\nname="fixture"\nversion="0.0.0"\n')
    for group in builder.FORMAL_COUNTS:
        identifier = group.replace("/", "_")
        helper.dump(root, f"results/{group}/records/{identifier}.json", {"run_id": identifier, "backend_type": "synthetic_test_fixture"})
        helper.dump(root, f"results/{group}/experiment_manifest.json", {"planned_runs": 1, "runtime_sha256": "synthetic_fixture"})
        helper.put(root, f"results/{group}/metrics.jsonl", json.dumps({"run_id": identifier}) + "\n")
        helper.dump(root, f"results/{group}/summary.json", {"total_runs": 1})
    original = "results/development_v3/records/18f1f34fcc3ae112629d286a.json"
    helper.dump(root, original, {"backend_type": "synthetic_test_fixture"})
    helper.dump(root, "results/demo/records/development_recovery.json", {"source_record_path": original, "source_record_sha256": builder.sha(root / original), "evidence_note": "development_v3 synthetic fixture"})
    helper.dump(root, "demo/selected_evidence.json", {"old": {"path": "results/demo/records/development_recovery.json"}})
    for name in ["demo/video_validation.json", "demo/playback_validation.json"]:
        helper.dump(root, name, {"project_version": "0.0.0", "valid": True, "all_passed": True, "video_sha256": builder.sha(root / "demo/demo.mp4"), "srt_sha256": builder.sha(root / "demo/demo_subtitles.srt")})
    helper.dump(root, "docs/qa/document_validation.json", {"project_version": "0.0.0", "pages": 1, "docx_sha256": builder.sha(root / "dist/project_report.docx"), "pdf_sha256": builder.sha(root / "dist/project_report.pdf"), "source_markdown_sha256": builder.sha(root / "docs/project_report.md"), "visual_review": "synthetic fixture only"})
    for folder in ["data", "data/v2"]:
        helper.dump(root, folder + "/frozen_manifest.json", {"frozen": True, "files": {name: builder.sha(root / folder / name) for name in ["test.jsonl", "dev.jsonl"]}})
    helper.dump(root, "results/v2/validation/experiment_integrity.json", {"all_passed": True, "scope": "synthetic fixture only"})
    helper.dump(root, "results/v2/launcher/validation/actual_windows_validation.json", {"version": "0.0.0", "all_passed": True, "checks": {"synthetic_fixture": True}, "steps": [{"pid": 1234}]})
    helper.make_frontend_fixture(root); helper.make_production_fixture(root, "0.0.0"); helper.make_manual_fixture(root, "0.0.0"); helper.make_feature_fixture(root, "0.0.0")
    helper.put(root, ".gitattributes", "*.json text\n")
    helper.put(root, "results/environment/hardware.json", '{"scope":"private fixture diagnostic"}')
    return builder


def add_visual_review_references(root):
    name = "demo/core_features/visual_review.json"
    review = json.loads((root / name).read_text(encoding="utf-8"))
    targets = ["demo/video_validation.json", "demo/playback_validation.json"]
    review["technical_evidence"] = {str(i): {"path": target, "sha256": publication.digest((root / target).read_bytes())} for i, target in enumerate(targets)}
    (root / name).write_bytes(publication.encoded(review))
    index = {"visual_review": name, "visual_review_sha256": publication.digest((root / name).read_bytes()), "scope": "synthetic test fixture only"}
    (root / "demo/final_recording_metadata.json").write_bytes(publication.encoded(index))
    return name, targets


def test_public_review_and_downstream_index_bind_projected_evidence_without_rewriting_source(tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "public"
    source.mkdir(); minimal_delivery(source, monkeypatch)
    name, targets = add_visual_review_references(source)
    originals = {path: (source / path).read_bytes() for path in [name, *targets, "demo/final_recording_metadata.json"]}
    publication.prepare(source, target)
    published = json.loads((target / name).read_text(encoding="utf-8"))
    assert published["publication_reference_projection"]["source_review_sha256"] == publication.digest(originals[name])
    for item in published["technical_evidence"].values():
        actual_public = (target / item["path"]).read_bytes()
        assert actual_public != originals[item["path"]]
        assert item["sha256"] == publication.digest(actual_public)
        assert item["original_source_sha256"] == publication.digest(originals[item["path"]])
    index = json.loads((target / "demo/final_recording_metadata.json").read_text(encoding="utf-8"))
    assert index["visual_review_sha256"] == publication.digest((target / name).read_bytes())
    assert index["visual_review_original_source_sha256"] == publication.digest(originals[name])
    assert all((source / path).read_bytes() == content for path, content in originals.items())


@pytest.mark.parametrize("failure", ["missing", "stale"])
def test_public_projection_rejects_missing_or_stale_source_review_reference(tmp_path, monkeypatch, failure):
    minimal_delivery(tmp_path, monkeypatch)
    name, _ = add_visual_review_references(tmp_path)
    review = json.loads((tmp_path / name).read_text(encoding="utf-8"))
    if failure == "missing":
        review["technical_evidence"]["0"]["path"] = "demo/nonexistent.json"
    else:
        review["technical_evidence"]["0"]["sha256"] = "0" * 64
    (tmp_path / name).write_bytes(publication.encoded(review))
    with pytest.raises(ValueError, match="public target is missing|source evidence hash is stale"):
        publication.plan(tmp_path, validate=False)


def test_public_snapshot_retains_raw_records_repackages_and_checks_actual_git_index(tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "public"
    source.mkdir()
    builder = minimal_delivery(source, monkeypatch)
    original = (source / "results/main/records/main.json").read_bytes()
    receipt = publication.prepare(source, target)
    assert not (target / ".git").exists()
    assert receipt["formal_record_counts"] == {"main": 1, "ablation": 1, "v2/baseline": 1, "v2/external": 1}
    assert (target / "results/main/records/main.json").read_bytes() == original
    assert not (target / "results/environment/hardware.json").exists()
    assert json.loads((target / "results/v2/launcher/validation/actual_windows_validation.json").read_text())["publication_summary"]
    # New local diagnostics must not enter a default rebuild of the public tree.
    diagnostic = target / "results/environment/hardware.json"
    diagnostic.parent.mkdir(parents=True)
    diagnostic.write_text('{"private":"synthetic local diagnostic"}', encoding="utf-8")
    assert diagnostic not in builder.select_files(target, "light")[0]
    archive = builder.build(target)
    assert (target / archive["path"]).is_file()
    git(target, "init", "--quiet")
    pathspec = source / "results/publication/public_git_pathspec.nul"
    git(target, "--literal-pathspecs", "add", "-f", "--pathspec-from-file=" + str(pathspec), "--pathspec-file-nul")
    assert publication.verify_tracking(target)["all_passed"]
    # A staged stale blob cannot masquerade as publishing current on-disk bytes.
    file = target / "results/main/records/main.json"
    file.write_bytes(b'{"different":"synthetic"}')
    git(target, "add", "-f", "results/main/records/main.json")
    file.write_bytes(original)
    with pytest.raises(ValueError, match="Git index bytes differ"):
        publication.verify_tracking(target)
    with pytest.raises(ValueError, match="new directory"):
        publication.prepare(source, target)


def existing_public_fixture(tmp_path, monkeypatch):
    source, target, staging = tmp_path / "source", tmp_path / "existing-public", tmp_path / "staging"
    source.mkdir()
    minimal_delivery(source, monkeypatch)
    for name in ("docs/remote_note.md", "scripts/reproduce.py"):
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("original synthetic content\n", encoding="utf-8")
    publication.prepare(source, target)
    git(target, "init", "--quiet")
    git(target, "config", "user.name", "Synthetic Fixture")
    git(target, "config", "user.email", "fixture@example.invalid")
    git(target, "add", "-f", "."); git(target, "commit", "--quiet", "-m", "synthetic published baseline")
    git(target, "tag", "v2.0.0")
    git(target, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(target, "checkout", "--quiet", "-b", "codex/fixture-update")
    return source, target, staging


def test_sync_preserves_remote_only_edits_and_new_files_without_reinitializing_history(tmp_path, monkeypatch):
    source, target, staging = existing_public_fixture(tmp_path, monkeypatch)
    (target / "docs/remote_note.md").write_text("remote author's newer content\n", encoding="utf-8")
    (target / "docs/remote_added.md").write_text("remote addition\n", encoding="utf-8")
    git(target, "add", "docs"); git(target, "commit", "--quiet", "-m", "synthetic remote changes")
    git(target, "update-ref", "refs/remotes/origin/main", "HEAD")
    head_before = git(target, "rev-parse", "HEAD")
    (source / "scripts/reproduce.py").write_text("new local delivery helper\n", encoding="utf-8")
    publication.prepare(source, staging)
    plan = publication.synchronization_plan(staging, target)
    assert plan["all_passed"] and plan["deletions"] == []
    result = publication.apply_synchronization(plan)
    assert result["preserved_remote"] == 2 and not result["git_committed"]
    assert (target / "docs/remote_note.md").read_text() == "remote author's newer content\n"
    assert (target / "docs/remote_added.md").read_text() == "remote addition\n"
    assert (target / "scripts/reproduce.py").read_bytes() == (source / "scripts/reproduce.py").read_bytes()
    assert git(target, "rev-parse", "HEAD") == head_before
    assert git(target, "rev-list", "--count", "HEAD").strip() == b"2"
    manifest = json.loads((target / "PUBLICATION_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["files"]["docs/remote_added.md"]["kind"] == "preserved_public_branch_file"
    assert manifest["synchronization"]["history_strategy"] == "existing_public_main_branch_pr_squash_merge"
    assert publication.readme_links({name: (target / name).read_bytes() for name in manifest["files"]})["all_passed"]


def test_sync_detects_dual_edit_and_does_not_overwrite_either_side(tmp_path, monkeypatch):
    source, target, staging = existing_public_fixture(tmp_path, monkeypatch)
    (target / "docs/remote_note.md").write_text("remote edit", encoding="utf-8")
    git(target, "add", "docs/remote_note.md"); git(target, "commit", "--quiet", "-m", "remote edit")
    (source / "docs/remote_note.md").write_text("different source edit", encoding="utf-8")
    publication.prepare(source, staging)
    plan = publication.synchronization_plan(staging, target)
    assert plan["conflicts"] == [{"path": "docs/remote_note.md", "reason": "both_source_and_public_branch_changed"}]
    before = git(target, "status", "--porcelain")
    with pytest.raises(ValueError, match="unresolved conflicts"):
        publication.apply_synchronization(plan)
    assert git(target, "status", "--porcelain") == before == b""
    assert (target / "docs/remote_note.md").read_text() == "remote edit"


@pytest.mark.parametrize("change", ["dirty_target", "stale_staging", "formal_record"])
def test_sync_rejects_unreviewed_inputs_and_preserves_formal_bytes(tmp_path, monkeypatch, change):
    source, target, staging = existing_public_fixture(tmp_path, monkeypatch)
    publication.prepare(source, staging)
    plan = publication.synchronization_plan(staging, target)
    record_name = "results/main/records/main.json"
    original = (target / record_name).read_bytes()
    if change == "dirty_target":
        (target / "docs/remote_note.md").write_text("uncommitted user work", encoding="utf-8")
        with pytest.raises(ValueError, match="must have no"):
            publication.apply_synchronization(plan)
    elif change == "stale_staging":
        (staging / "scripts/reproduce.py").write_text("changed after review", encoding="utf-8")
        with pytest.raises(ValueError, match="differs from reviewed manifest"):
            publication.apply_synchronization(plan)
    else:
        (staging / record_name).write_bytes(original + b" ")
        manifest_path = staging / "PUBLICATION_MANIFEST.json"
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        value["files"][record_name]["sha256"] = publication.digest((staging / record_name).read_bytes())
        manifest_path.write_bytes(publication.encoded(value))
        plan = publication.synchronization_plan(staging, target)
        assert any(c["reason"] == "formal_record_bytes_are_immutable" for c in plan["conflicts"])
        with pytest.raises(ValueError, match="unresolved conflicts"):
            publication.apply_synchronization(plan)
    assert (target / record_name).read_bytes() == original


def test_release_build_binding_requires_clean_fetched_main_not_only_a_staged_manifest(tmp_path):
    git(tmp_path, "init", "--quiet")
    git(tmp_path, "config", "user.name", "Synthetic Fixture")
    git(tmp_path, "config", "user.email", "fixture@example.invalid")
    file = tmp_path / "README.md"; file.write_text("synthetic main", encoding="utf-8")
    git(tmp_path, "add", "README.md"); git(tmp_path, "commit", "--quiet", "-m", "synthetic main")
    git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert publication.verify_public_main(tmp_path)["clean_checkout"]
    file.write_text("staged but not committed", encoding="utf-8"); git(tmp_path, "add", "README.md")
    with pytest.raises(ValueError, match="clean checkout"):
        publication.verify_public_main(tmp_path)
    git(tmp_path, "commit", "--quiet", "-m", "synthetic unmerged feature branch")
    with pytest.raises(ValueError, match="after PR merge"):
        publication.verify_public_main(tmp_path)


def test_tracking_checks_publication_manifest_index_bytes_as_well_as_payload(tmp_path):
    git(tmp_path, "init", "--quiet")
    raw = b"synthetic reviewed source"
    (tmp_path / "README.md").write_bytes(raw)
    manifest = {"files": {"README.md": {"sha256": publication.digest(raw)}}, "formal_record_counts": {}}
    path = tmp_path / "PUBLICATION_MANIFEST.json"; path.write_bytes(publication.encoded(manifest))
    git(tmp_path, "add", "README.md", "PUBLICATION_MANIFEST.json")
    assert publication.verify_tracking(tmp_path)["all_passed"]
    manifest["source_commit"] = "changed manifest metadata that was not staged"
    path.write_bytes(publication.encoded(manifest))
    with pytest.raises(ValueError, match="current PUBLICATION_MANIFEST"):
        publication.verify_tracking(tmp_path)
