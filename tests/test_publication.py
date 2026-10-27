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
    helper.make_frontend_fixture(root); helper.make_production_fixture(root, "0.0.0"); helper.make_manual_fixture(root, "0.0.0")
    helper.put(root, ".gitattributes", "*.json text\n")
    helper.put(root, "results/environment/hardware.json", '{"scope":"private fixture diagnostic"}')
    return builder


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
