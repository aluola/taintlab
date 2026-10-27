"""Isolated acceptance-harness regressions; never operate project services.

Only copied CMDs in empty temporary folders may be executed. They cannot reach
the lifecycle manager because their local .venv and scripts are absent.
"""
from __future__ import annotations

import json
import os
from contextlib import nullcontext
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import verify_launcher_windows as validation
import verify_model_offline_windows as offline_validation

REAL_ACTIVATE = validation.activate_cmd
REAL_RUN = subprocess.run
REAL_POPEN = subprocess.Popen


@pytest.fixture(autouse=True)
def no_real_services(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Isolated acceptance tests must not operate actual services")
    monkeypatch.setattr(validation, "Project", forbidden)
    monkeypatch.setattr(offline_validation, "Project", forbidden)
    monkeypatch.setattr(validation, "activate_cmd", forbidden)
    monkeypatch.setattr(validation.subprocess, "Popen", forbidden)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def campaign_root(tmp_path):
    root = tmp_path / "isolated"
    planned = {"baseline": 2, "external": 1}
    write(root / "configs/experiment_v2.lock.json", {"signature": {"planned_runs": planned, "runtime_sha256": "unit-fixture-hash"}})
    for name, count in planned.items():
        folder = root / "results/v2" / name
        write(folder / "experiment_manifest.json", {"planned_runs": count, "runtime_sha256": "unit-fixture-hash", "backend_type": "local_llama_cpp"})
        write(folder / "summary.json", {"fixture": True})
        (folder / "metrics.jsonl").write_text("{}\n" * count, encoding="utf-8")
        for index in range(count):
            write(folder / "records" / f"fixture_{index}.json", {"synthetic_unit_fixture": True})
    return root


def test_no_execute_flag_cannot_reach_a_process_operation():
    with pytest.raises(SystemExit) as error:
        validation.main([])
    assert error.value.code == 2


def test_offline_UI_requires_explicit_execute_before_process_operation():
    with pytest.raises(SystemExit) as error:
        offline_validation.main([])
    assert error.value.code == 2


def test_offline_active_run_check_is_read_only_and_excludes_completed(tmp_path):
    path = tmp_path / 'sessions.sqlite'
    connection = sqlite3.connect(path)
    try:
        connection.execute('CREATE TABLE runs (data TEXT)')
        connection.executemany('INSERT INTO runs VALUES (?)', [(json.dumps({'record': {'status': status}}),) for status in ('completed', 'pending', 'running', 'stopping')])
        connection.commit()
    finally:
        connection.close()
    before = path.read_bytes()
    assert offline_validation.active_runs(path) == 2
    assert path.read_bytes() == before
    assert offline_validation.active_runs(tmp_path / 'missing.sqlite') == 0
    assert not (tmp_path / 'missing.sqlite').exists()


@pytest.mark.skipif(os.name != 'nt', reason='Actual integration entry is Windows-only')
def test_offline_UI_active_run_gate_cannot_stop_a_model(campaign_root, monkeypatch):
    monkeypatch.setattr(offline_validation, 'ROOT', campaign_root)
    monkeypatch.setattr(offline_validation.shutil, 'which', lambda _: 'isolated-node-fixture')
    monkeypatch.setattr(offline_validation, 'active_runs', lambda _: 1)
    with pytest.raises(RuntimeError, match='Interactive runs are active'):
        offline_validation.main(['--execute'])
    assert not (campaign_root / 'results/v2/browser').exists()


@pytest.mark.skipif(os.name != 'nt', reason='Actual integration entry is Windows-only')
def test_offline_UI_failed_browser_still_restores_exact_model_and_reuses_UI(campaign_root, monkeypatch):
    model = {'pid': 101, 'created': 'model-fixture'}
    ui = {'pid': 102, 'created': 'ui-fixture'}
    calls = []
    class FakeProject:
        def __init__(self):
            self.root = campaign_root
            self.settings = {'operation_lock_timeout_seconds': 1}
            self.events = []
            self.model_stopped = False
        def inspect(self):
            return {'model': {'healthy': not self.model_stopped, 'conflicts': [], 'owned': [] if self.model_stopped else [model], 'listeners': [] if self.model_stopped else [101]},
                    'ui': {'healthy': True, 'conflicts': [], 'owned': [ui], 'listeners': [102]}}
        def stop_identity(self, kind, identity, reason):
            assert kind == 'model' and identity == model
            self.model_stopped = True
            calls.append('verified-model-stop')
        def start(self, open_browser):
            assert open_browser is False
            self.model_stopped = False
            calls.append('model-restored-existing-UI')
            return self.inspect()
    def browser_run(command, **kwargs):
        calls.append(command[-1])
        return SimpleNamespace(returncode=1 if command[-1] == 'offline' else 0)
    monkeypatch.setattr(offline_validation, 'ROOT', campaign_root)
    monkeypatch.setattr(offline_validation, 'Project', FakeProject)
    monkeypatch.setattr(offline_validation, 'project_mutex', lambda *args: nullcontext())
    monkeypatch.setattr(offline_validation.shutil, 'which', lambda _: 'isolated-node-fixture')
    monkeypatch.setattr(offline_validation.subprocess, 'run', browser_run)
    assert offline_validation.main(['--execute']) == 1
    assert calls == ['verified-model-stop', 'offline', 'model-restored-existing-UI', 'restored']
    report = json.loads((campaign_root / 'results/v2/browser/model-offline-lifecycle.json').read_text(encoding='utf-8'))
    assert not report['all_passed'] and report['same_UI_identity'] and report['protected_unchanged']
    assert report['restored_browser_exit_code'] == 0 and 'error' in report


@pytest.mark.skipif(os.name != "nt", reason="Actual integration entry is Windows-only")
def test_incomplete_frozen_campaign_blocks_execute_before_project_construction(tmp_path, monkeypatch):
    monkeypatch.setattr(validation, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="冻结锁"):
        validation.main(["--execute"])
    assert not (tmp_path / validation.VALIDATION_DIRECTORY).exists()


def test_completed_campaign_gate_reads_only_saved_indices(campaign_root):
    result = validation.verify_frozen_campaigns(campaign_root)
    assert result["baseline"]["records"] == 2 and result["external"]["metrics"] == 1


@pytest.mark.parametrize("problem", ["missing_record", "missing_summary", "metrics_count", "manifest_count", "runtime_changed", "scripted_backend", "unsafe_campaign_key"])
def test_incomplete_or_mismatched_batch_is_rejected_without_process_operations(campaign_root, problem):
    folder = campaign_root / "results/v2/baseline"
    if problem == "missing_record":
        (folder / "records/fixture_1.json").unlink()
    elif problem == "missing_summary":
        (folder / "summary.json").unlink()
    elif problem == "metrics_count":
        (folder / "metrics.jsonl").write_text("{}\n", encoding="utf-8")
    elif problem == "unsafe_campaign_key":
        write(campaign_root / "configs/experiment_v2.lock.json", {"signature": {"planned_runs": {"../elsewhere": 1}, "runtime_sha256": "unit-fixture-hash"}})
    else:
        manifest = json.loads((folder / "experiment_manifest.json").read_text())
        manifest[{"manifest_count": "planned_runs", "runtime_changed": "runtime_sha256", "scripted_backend": "backend_type"}[problem]] = {"manifest_count": 3, "runtime_changed": "other", "scripted_backend": "scripted_test"}[problem]
        write(folder / "experiment_manifest.json", manifest)
    with pytest.raises(RuntimeError):
        validation.verify_frozen_campaigns(campaign_root)


def test_protected_hash_covers_all_versions_licenses_and_old_validation_but_not_new_runtime(campaign_root):
    root = campaign_root
    keep = ["data/test.jsonl", "data/v2/source/NOTICE.md", "results/main/records/old.json", "results/ablation/records/old.json", "results/launcher/validation/old.json"]
    for name in keep:
        write(root / name, {"historical_fixture": True})
    excluded = ["results/v2/launcher/state.json", "results/v2/launcher/validation/current.json", "results/v2/web_private/session.json"]
    for name in excluded:
        write(root / name, {"runtime_fixture": True})
    selected = {path.relative_to(root).as_posix() for path in validation.protected_files(root)}
    assert set(keep) <= selected and not set(excluded) & selected
    before = validation.protected_hash(root)
    assert before["formal_records"] == {"results/main": 1, "results/ablation": 1, "results/v2/baseline": 2, "results/v2/external": 1}
    write(root / excluded[0], {"runtime_fixture": "changed"})
    assert validation.protected_hash(root) == before
    write(root / keep[1], {"license_fixture": "changed"})
    assert validation.protected_hash(root)["sha256"] != before["sha256"]


def test_acceptance_output_directory_is_versioned():
    assert validation.VALIDATION_DIRECTORY == "results/v2/launcher/validation"
    assert validation.VERSION == "2.0.0"


class NativeFunction:
    def __init__(self, function):
        self.function = function
    def __call__(self, *args):
        return self.function(*args)


@pytest.mark.skipif(os.name != "nt", reason="Windows native file-association structure")
def test_native_activation_is_hidden_and_uses_exact_cmd_with_explicit_arguments(monkeypatch, tmp_path):
    captured, closed = {}, []
    def activate(pointer):
        info = pointer._obj
        captured.update(file=info.lpFile, parameters=info.lpParameters, directory=info.lpDirectory, visibility=info.nShow)
        info.hProcess = 12345
        return 1
    def exit_code(handle, pointer):
        assert handle == 12345
        pointer._obj.value = 0
        return 1
    shell = SimpleNamespace(ShellExecuteExW=NativeFunction(activate))
    kernel = SimpleNamespace(WaitForSingleObject=NativeFunction(lambda handle, milliseconds: 0),
                             GetExitCodeProcess=NativeFunction(exit_code), CloseHandle=NativeFunction(lambda handle: closed.append(handle) or 1))
    monkeypatch.setattr(validation.ctypes, "WinDLL", lambda name, **kwargs: shell if name == "shell32" else kernel)
    monkeypatch.setattr(validation, "ROOT", tmp_path)
    result = REAL_ACTIVATE("start", no_browser=True)
    assert captured["file"] == str(tmp_path / "启动项目.cmd")
    assert captured["parameters"] == "--non-interactive --no-browser" and captured["visibility"] == 0
    assert result["exit_code"] == 0 and result["launcher_exited"]
    assert closed == [12345]


@pytest.mark.parametrize("entry", ["启动项目.cmd", "关闭项目.cmd"])
@pytest.mark.skipif(os.name != "nt", reason="Isolated Windows CMD execution")
def test_copied_cmd_without_venv_fails_and_logs_only_under_v2(entry, tmp_path, monkeypatch):
    isolated = tmp_path / "缺失环境 中文 & space (isolated)"
    isolated.mkdir()
    target = isolated / entry
    shutil.copyfile(SCRIPTS.parent / entry, target)
    assert not (isolated / ".venv").exists() and not (isolated / "scripts").exists()
    # Permit only this copied, missing-environment CMD's process creation.
    monkeypatch.setattr(validation.subprocess, "Popen", REAL_POPEN)
    command = f'"{os.environ["COMSPEC"]}" /d /s /c ""{target}" --non-interactive"'
    result = REAL_RUN(command, cwd=tmp_path, capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    assert result.returncode != 0 and "缺少项目虚拟环境" in output and "install.ps1" in output
    log = isolated / "results/v2/launcher/entry_errors.log"
    assert log.is_file() and "Missing environment" in log.read_text(encoding="utf-8")
    assert not (isolated / "results/launcher").exists()
