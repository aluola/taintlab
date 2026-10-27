"""Isolated launcher regressions. No test queries or terminates real processes."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Project lifecycle entry points are Windows-only")

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import launch_model as model_launcher
import project_lifecycle as lifecycle

REAL_TERMINATE_EXACT = lifecycle.WindowsSystem.terminate_exact
REAL_HTTP_HEALTH = lifecycle.WindowsSystem.http_health


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class FakeSystem:
    def __init__(self):
        self.processes = []
        self.listeners = []
        self.health = {"model": True, "ui": True}
        self.terminated = []
        self.browsers = []
        self.health_checks = []

    def snapshot(self, ports):
        return {"processes": deepcopy(self.processes), "listeners": deepcopy(self.listeners)}

    def http_health(self, kind, port):
        self.health_checks.append((kind, port))
        return self.health[kind]

    def spawn_identity(self, process):
        return {"pid": process.pid, "exe": process.exe, "created": process.created}

    def terminate_exact(self, identity, timeout):
        current = next((p for p in self.processes if p["pid"] == identity["pid"]), None)
        assert current and lifecycle.same_creation(current["created"], identity["created"])
        assert lifecycle.norm(current["exe"]) == lifecycle.norm(identity["exe"])
        self.terminated.append(deepcopy(identity))
        self.processes = [p for p in self.processes if p["pid"] != identity["pid"]]
        self.listeners = [p for p in self.listeners if p["pid"] != identity["pid"]]
        return "terminated_and_waited"

    def open_browser(self, url):
        self.browsers.append(url)

    def add(self, project, kind, pid, *, created="133900000000000000", address="127.0.0.1", listening=True):
        process = {"pid": pid, "exe": project.commands[kind][0], "argv": list(project.commands[kind]), "created": created}
        self.processes.append(process)
        if listening:
            self.listeners.append({"port": project.ports[kind], "address": address, "pid": pid})
        return process


@pytest.fixture(autouse=True)
def prevent_real_process_operations(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Launcher tests must never operate real processes")
    monkeypatch.setattr(lifecycle.subprocess, "Popen", forbidden)
    monkeypatch.setattr(lifecycle.subprocess, "run", forbidden)
    monkeypatch.setattr(lifecycle, "powershell_json", forbidden)
    monkeypatch.setattr(lifecycle.WindowsSystem, "terminate_exact", forbidden)
    monkeypatch.setattr(lifecycle.WindowsSystem, "open_browser", forbidden)
    monkeypatch.setattr(lifecycle.WindowsSystem, "http_health", forbidden)
    monkeypatch.setattr(lifecycle.WindowsSystem, "spawn_identity", forbidden)


@pytest.fixture
def project_root(tmp_path):
    root = tmp_path / "中文 workspace (isolated)"
    config = {
        "endpoint": "http://127.0.0.1:18080/v1", "model": "qwen3-0.6b",
        "context_size": 4096, "max_tokens": 512, "temperature": 0.2,
        "top_p": 0.9, "top_k": 40, "min_p": 0.05, "repeat_penalty": 1.0,
        "enable_thinking": False, "server_parallel_slots": 4,
    }
    lock = {
        **{k: config[k] for k in ("context_size", "max_tokens", "temperature", "top_p", "top_k", "min_p", "repeat_penalty")},
        "model_file": "models/test Q8_0.gguf", "server_file": "runtime/bin/llama-server.exe",
        "model_size_bytes": 5, "thinking": False, "parallel_slots": 4,
        "server_context_size": 16384, "gpu_layers": 99,
    }
    write_json(root / "configs/model.json", config)
    write_json(root / "configs/model.lock.json", lock)
    write_json(root / "configs/launcher.json", {"ui_port": 18501, "startup_timeout_seconds": 1, "stop_timeout_seconds": 1, "operation_lock_timeout_seconds": 1})
    for name in (".venv/Scripts/python.exe", "scripts/launch_model.py", "scripts/project_lifecycle.py", "scripts/start_model.ps1", "scripts/start_ui.ps1", "scripts/stop_model.ps1", "scripts/serve_app.py", "src/taintlab/ui/app.py", "src/taintlab/__init__.py", "frontend/dist/assets/app.js", "frontend/dist/assets/app.css", lock["server_file"]):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"isolated placeholder")
    (root / "frontend/dist/index.html").write_text('<html><script type="module" src="/assets/app.js"></script><link rel="stylesheet" href="/assets/app.css"></html>', encoding="utf-8")
    path = root / lock["model_file"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"gguf!")
    return root


@pytest.fixture
def project(project_root):
    return lifecycle.Project(project_root, FakeSystem())


def dependency_response(project, *, missing=None, origin=None, version=None, returncode=0):
    names = ["fastapi", "uvicorn", "python_multipart", "pypdf", "pydantic", "httpx", "pandas", "matplotlib", "taintlab"]
    modules = {name: str(project.root / f".venv/Lib/site-packages/{name}/__init__.py") for name in names}
    modules["taintlab"] = str(origin or project.root / "src/taintlab/__init__.py")
    if missing:
        modules[missing] = None
    return SimpleNamespace(returncode=returncode, stdout=json.dumps({"version": version or [3, 12], "modules": modules}).encode(), stderr=b"")


def add_venv_ui_chain(project, parent_pid=901, child_pid=902):
    parent = project.system.add(project, "ui", parent_pid, created="133900000000000520", listening=False)
    child = project.system.add(project, "ui", child_pid, created="133900000000000530")
    child["parent_pid"] = parent_pid
    child["exe"] = str(project.base_python)
    child["argv"][0] = str(project.base_python)
    return parent, child


@pytest.mark.skipif(os.name != "nt", reason="Windows command-line parser is platform-specific")
def test_windows_command_line_round_trip_keeps_spaces_quotes_unicode_and_trailing_slash():
    argv = [r"D:\中文 project\python.exe", "-m", "streamlit", "run", r"D:\中文 project\ui\app.py", "--label", 'value with "quotes"', "--directory", "D:\\path with spaces\\", "--json", '{"enable_thinking":false}']
    assert lifecycle.split_command_line(subprocess.list2cmdline(argv)) == argv


@pytest.mark.parametrize("entry", ["启动项目.cmd", "关闭项目.cmd"])
def test_cmd_workspace_substitutions_remain_quoted_with_metacharacters(entry):
    # Static command-boundary regression; actual CMD execution is separately
    # validated by the main agent. No command from this test is executed.
    hypothetical_root = "C:\\中文 workspace & isolated (test)\\"
    text = (SCRIPTS.parent / entry).read_text(encoding="utf-8-sig")
    substitutions = 0
    for line in text.splitlines():
        if "%~dp0" not in line:
            continue
        expanded = line.replace("%~dp0", hypothetical_root)
        offset = 0
        while (index := expanded.find(hypothetical_root, offset)) >= 0:
            substitutions += 1
            for relative, character in enumerate(hypothetical_root):
                if character in "&()":
                    assert expanded[:index + relative].count('"') % 2 == 1, f"Unquoted CMD path metacharacter: {line}"
            offset = index + len(hypothetical_root)
    assert substitutions >= 5


@pytest.mark.parametrize("entry", ["启动项目.cmd", "关闭项目.cmd"])
def test_cmd_missing_environment_and_helpers_are_logged_before_python_entry(entry):
    # This static contract supplements the main agent's actual CMD validation.
    text = (SCRIPTS.parent / entry).read_text(encoding="utf-8-sig")
    execute_index = text.index('"%~dp0.venv\\Scripts\\python.exe" -u ')
    for required in (".venv\\Scripts\\python.exe", "scripts\\project_lifecycle.py", "scripts\\launch_model.py"):
        guard = f'if not exist "%~dp0{required}" ('
        guard_index = text.index(guard)
        assert guard_index < execute_index
        block = text[guard_index:].split("\n)", 1)[0]
        assert '>>"%~dp0results\\v2\\launcher\\entry_errors.log" echo ' in block
        assert "exit /b 1" in block
        assert required in block


def test_model_and_ui_commands_bind_absolute_workspace_and_loopback(project):
    command = project.commands["model"]
    assert Path(command[0]).is_absolute()
    assert Path(command[command.index("-m") + 1]).is_absolute()
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "18080"
    assert command[command.index("-c") + 1] == "16384"
    assert command[command.index("-np") + 1] == "4"
    assert command[command.index("-ngl") + 1] == "99"
    assert command[command.index("--reasoning") + 1] == "off"
    assert "--no-context-shift" in command and "--no-webui" in command
    ui = project.commands["ui"]
    assert ui[0] == str(project.root / ".venv/Scripts/python.exe")
    assert ui[1] == str(project.root / "scripts/serve_app.py")
    assert ui[ui.index("--host") + 1] == "127.0.0.1"
    assert ui[ui.index("--port") + 1] == "18501"
    assert "streamlit" not in ui


@pytest.mark.parametrize("mutation", ["foreign_exe", "foreign_model", "wrong_port", "missing_argument", "extra_argument", "empty_birth", "relative_exe", "relative_model"])
def test_ownership_requires_complete_arguments_and_absolute_project_paths(project, mutation):
    process = project.system.add(project, "model", 101)
    if mutation == "foreign_exe":
        process["exe"] = str(project.root.parent / "other/llama-server.exe")
    elif mutation == "foreign_model":
        process["argv"][2] = str(project.root.parent / "other/model.gguf")
    elif mutation == "wrong_port":
        process["argv"][process["argv"].index("--port") + 1] = "28080"
    elif mutation == "missing_argument":
        process["argv"].pop()
    elif mutation == "extra_argument":
        process["argv"].append("--metrics")
    elif mutation == "empty_birth":
        process["created"] = ""
    elif mutation == "relative_exe":
        process["exe"] = "runtime/bin/llama-server.exe"
    else:
        process["argv"][2] = "models/test Q8_0.gguf"
    assert not project.owned(process, "model")


@pytest.mark.skipif(os.name != "nt", reason="Windows path casing")
def test_owned_windows_paths_allow_equivalent_case_without_relaxing_arguments(project):
    process = project.system.add(project, "model", 102)
    process["exe"] = process["exe"].upper()
    process["argv"][0] = process["argv"][0].upper()
    process["argv"][2] = process["argv"][2].upper().replace("\\", "/")
    assert project.owned(process, "model")


@pytest.mark.parametrize("problem", ["no_listener", "public_listener", "other_listener", "duplicate_owned", "http_failure"])
def test_health_requires_single_owner_local_listener_and_successful_http(project, problem):
    project.system.add(project, "model", 110, listening=problem != "no_listener", address="0.0.0.0" if problem == "public_listener" else "127.0.0.1")
    if problem == "other_listener":
        project.system.listeners.append({"port": 18080, "address": "127.0.0.1", "pid": 999})
    elif problem == "duplicate_owned":
        project.system.add(project, "model", 111, listening=False)
    elif problem == "http_failure":
        project.system.health["model"] = False
    assert not project.inspect()["model"]["healthy"]


@pytest.mark.parametrize("kind", ["model", "ui"])
def test_unknown_port_conflict_stops_start_before_spawn_or_termination(project, monkeypatch, kind):
    if kind == "ui":
        project.system.add(project, "model", 109)
    project.system.listeners.append({"port": project.ports[kind], "address": "127.0.0.1", "pid": 999})
    monkeypatch.setattr(project, "preflight", lambda: None)
    calls = []
    monkeypatch.setattr(project, "spawn", lambda service: calls.append(service))
    with pytest.raises(lifecycle.LifecycleError, match="端口冲突"):
        project.start()
    assert calls == [] and project.system.terminated == [] and project.system.browsers == []


def test_unhealthy_existing_project_service_is_not_silently_replaced(project, monkeypatch):
    project.system.add(project, "model", 120)
    project.system.health["model"] = False
    monkeypatch.setattr(project, "preflight", lambda: None)
    calls = []
    monkeypatch.setattr(project, "spawn", lambda kind: calls.append(kind))
    with pytest.raises(lifecycle.LifecycleError, match="不健康"):
        project.start()
    assert calls == [] and project.system.terminated == []
    assert project.system.processes[0]["pid"] == 120


def test_pid_files_and_state_are_non_authoritative_hints(project):
    write_json(project.state_path, {"services": {"model": {"pid": 999, "created": "old-birth"}}})
    legacy = project.root / "results/environment/model.pid"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("999", encoding="ascii")
    (project.root / "results/ui.pid").write_text("not-a-pid", encoding="ascii")
    project.system.processes.append({"pid": 999, "created": "new-birth", "exe": str(project.root.parent / "other.exe"), "argv": []})
    project.system.listeners.append({"port": 18080, "address": "127.0.0.1", "pid": 999})
    project.stop()
    assert project.system.terminated == []
    assert project.system.processes[0]["pid"] == 999
    events = {event["event"] for event in project.events}
    assert {"stale_or_mismatched_state", "stale_or_mismatched_legacy_pid", "invalid_legacy_pid_hint"} <= events


@pytest.mark.parametrize("state", [[], {"services": []}, {"services": {"model": None}}, None])
def test_malformed_state_shape_does_not_block_live_identity_based_stop(project, state):
    write_json(project.state_path, state)
    project.system.add(project, "model", 210)
    project.system.add(project, "ui", 211)
    project.stop()
    assert [p["pid"] for p in project.system.terminated] == [211, 210]
    assert any(event["event"] == "invalid_state_hint" for event in project.events)


@pytest.mark.parametrize("changed", ["birth", "arguments", "executable", "exited"])
def test_stop_identity_rechecks_current_identity_and_never_terminates_pid_reuse(project, changed):
    current = project.system.add(project, "model", 201)
    saved = deepcopy(current)
    if changed == "birth":
        current["created"] = "133900000000000010"
    elif changed == "arguments":
        current["argv"].append("--metrics")
    elif changed == "executable":
        current["exe"] = str(project.root.parent / "other.exe")
    else:
        project.system.processes.clear()
    project.stop_identity("model", saved, "test")
    assert project.system.terminated == []
    assert project.events[-1]["event"] == "termination_skipped_identity_changed_or_exited"


def test_stop_orders_ui_before_model_and_preserves_unrelated_processes(project):
    project.system.add(project, "model", 301)
    project.system.add(project, "ui", 302)
    project.system.processes.append({"pid": 999, "created": "other-birth", "exe": "C:\\other\\python.exe", "argv": ["other.py"]})
    project.system.listeners.append({"port": 18501, "address": "127.0.0.1", "pid": 999})
    project.stop()
    assert [p["pid"] for p in project.system.terminated] == [302, 301]
    assert [p["pid"] for p in project.system.processes] == [999]
    assert project.system.listeners[0]["pid"] == 999
    assert json.loads(project.state_path.read_text(encoding="utf-8"))["services"] == {}


def test_healthy_services_are_reused_and_only_verified_url_is_opened(project, monkeypatch):
    project.system.add(project, "model", 401)
    project.system.add(project, "ui", 402)
    monkeypatch.setattr(project, "preflight", lambda: None)
    calls = []
    monkeypatch.setattr(project, "spawn", lambda kind: calls.append(kind))
    project.start()
    assert calls == [] and project.system.terminated == []
    assert project.system.browsers == ["http://127.0.0.1:18501/"]
    saved = json.loads(project.state_path.read_text(encoding="utf-8"))["services"]
    assert saved["model"]["pid"] == 401 and saved["ui"]["pid"] == 402


def test_cold_start_orders_model_then_ui_and_commits_healthy_state(project, monkeypatch):
    monkeypatch.setattr(project, "preflight", lambda: None)
    order = []
    def spawn(kind):
        order.append(kind)
        identity = project.system.add(project, kind, 501 if kind == "model" else 502)
        project.created.append((kind, deepcopy(identity)))
        return project.inspect()
    monkeypatch.setattr(project, "spawn", spawn)
    status = project.start(open_browser=False)
    assert order == ["model", "ui"]
    assert all(item["healthy"] for item in status.values())
    assert project.system.browsers == [] and project.system.terminated == []


def test_venv_redirector_and_exact_base_python_child_count_as_one_healthy_ui(project):
    parent, child = add_venv_ui_chain(project)
    ui = project.inspect()["ui"]
    assert ui["healthy"]
    assert [p["pid"] for p in ui["owned"]] == [child["pid"]]
    assert [p["pid"] for p in ui["launchers"]] == [parent["pid"]]


@pytest.mark.parametrize("problem", ["wrong_app", "wrong_parent", "child_predates_parent"])
def test_venv_ui_chain_does_not_hide_unrelated_or_stale_parent_links(project, problem):
    parent, child = add_venv_ui_chain(project)
    if problem == "wrong_app":
        child["argv"][1] = str(project.root.parent / "other/serve_app.py")
    elif problem == "wrong_parent":
        child["parent_pid"] = 999
    else:
        child["created"] = "133900000000000510"
    ui = project.inspect()["ui"]
    assert not ui["healthy"]
    assert ui["launchers"] == []


def test_stop_ends_ui_server_and_redirector_before_model(project):
    project.system.add(project, "model", 900)
    add_venv_ui_chain(project)
    project.stop()
    assert [p["pid"] for p in project.system.terminated] == [902, 901, 900]


def test_new_ui_spawn_registers_verified_redirector_and_linked_child(project, monkeypatch):
    parent, child = add_venv_ui_chain(project)
    original = SimpleNamespace(pid=parent["pid"], exe=parent["exe"], created="133900000000000526", returncode=None, poll=lambda: None)
    monkeypatch.setattr(lifecycle.subprocess, "Popen", lambda *args, **kwargs: original)
    result = project.spawn("ui")
    assert result["ui"]["healthy"]
    assert [identity["pid"] for _, identity in project.created] == [901, 902]


def test_exited_ui_redirector_cannot_authorize_child_capture_from_stale_snapshot(project, monkeypatch):
    parent, child = add_venv_ui_chain(project)
    original = SimpleNamespace(pid=parent["pid"], exe=parent["exe"], created="133900000000000526", returncode=1, poll=lambda: 1)
    monkeypatch.setattr(lifecycle.subprocess, "Popen", lambda *args, **kwargs: original)
    with pytest.raises(lifecycle.LifecycleError, match="提前退出"):
        project.spawn("ui")
    assert [identity["pid"] for _, identity in project.created] == [901]


@pytest.mark.parametrize("reuse_model", [True, False])
def test_failure_rolls_back_only_new_captured_identities_in_reverse_order(project, monkeypatch, reuse_model):
    monkeypatch.setattr(project, "preflight", lambda: None)
    if reuse_model:
        project.system.add(project, "model", 601)
    def spawn(kind):
        identity = project.system.add(project, kind, 601 if kind == "model" else 602)
        project.created.append((kind, deepcopy(identity)))
        if kind == "ui":
            raise lifecycle.LifecycleError("simulated UI startup failure")
        return project.inspect()
    monkeypatch.setattr(project, "spawn", spawn)
    with pytest.raises(lifecycle.LifecycleError, match="simulated UI"):
        project.start()
    assert [p["pid"] for p in project.system.terminated] == ([602] if reuse_model else [602, 601])
    assert [p["pid"] for p in project.system.processes] == ([601] if reuse_model else [])
    assert project.system.browsers == []


def test_spawn_must_not_adopt_a_healthy_reused_pid_after_original_child_exit(project, monkeypatch):
    # Popen's original handle is exited; the OS reused its numeric PID for a
    # different creation time with the same command and a healthy listener.
    original = SimpleNamespace(pid=701, returncode=1, poll=lambda: 1, exe=project.commands["model"][0], created="133900000000000000")
    project.system.add(project, "model", 701, created="133900000000001000")
    monkeypatch.setattr(lifecycle, "spawn_model", lambda *args, **kwargs: original)
    with pytest.raises(lifecycle.LifecycleError):
        project.spawn("model")
    assert len(project.created) == 1
    assert project.created[0][1]["created"] == original.created
    project.stop_identity("model", project.created[0][1], "rollback_only_created_by_this_operation")
    assert project.system.terminated == []


def test_spawn_identity_mismatch_is_not_captured_even_before_exit_observed(project, monkeypatch):
    original = SimpleNamespace(pid=702, returncode=None, poll=lambda: None, exe=project.commands["model"][0], created="133900000000000000")
    project.system.add(project, "model", 702, created="133900000000001000")
    monkeypatch.setattr(lifecycle, "spawn_model", lambda *args, **kwargs: original)
    ticks = iter([0.0, 0.1, 2.0])
    monkeypatch.setattr(lifecycle.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(lifecycle.time, "sleep", lambda delay: None)
    with pytest.raises(lifecycle.LifecycleError, match="超时"):
        project.spawn("model")
    assert len(project.created) == 1 and project.created[0][1]["created"] == original.created
    project.stop_identity("model", project.created[0][1], "rollback_only_created_by_this_operation")
    assert project.system.terminated == []


def test_first_query_failure_cleans_only_original_child_and_preserves_initial_error(project, monkeypatch):
    monkeypatch.setattr(project, "preflight", lambda: None)
    project.system.processes.append({"pid": 999, "created": "133900000000000000", "exe": "C:\\other\\python.exe", "argv": ["other.py"]})
    def spawn(*args, **kwargs):
        project.system.add(project, "model", 720, created="133900000000000520", listening=False)
        return SimpleNamespace(pid=720, exe=project.commands["model"][0], created="133900000000000526", returncode=None, poll=lambda: None)
    monkeypatch.setattr(lifecycle, "spawn_model", spawn)
    original_snapshot = project.system.snapshot
    count = 0
    def snapshot(ports):
        nonlocal count
        count += 1
        if count == 1:
            return original_snapshot(ports)
        raise lifecycle.LifecycleError("initial_CIM_failure" if count == 2 else "secondary_CIM_failure")
    monkeypatch.setattr(project.system, "snapshot", snapshot)
    with pytest.raises(lifecycle.LifecycleError, match="initial_CIM_failure"):
        project.start(open_browser=False)
    assert [p["pid"] for p in project.system.terminated] == [720]
    assert [p["pid"] for p in project.system.processes] == [999]
    assert any(event["event"] == "rollback_state_refresh_failed" and "secondary_CIM_failure" in event["error"] for event in project.events)


@pytest.mark.parametrize("reason", ["explicit_project_stop", "rollback_only_created_by_this_operation"])
def test_cim_failure_cannot_authorize_fallback_for_an_identity_not_created_in_this_operation(project, monkeypatch, reason):
    existing = project.system.add(project, "model", 721)
    def unavailable(ports):
        raise lifecycle.LifecycleError("CIM unavailable")
    monkeypatch.setattr(project.system, "snapshot", unavailable)
    with pytest.raises(lifecycle.LifecycleError, match="CIM unavailable"):
        project.stop_identity("model", deepcopy(existing), reason)
    assert project.created == [] and project.system.terminated == []


def test_rollback_keeps_original_start_error_when_one_termination_fails(project, monkeypatch):
    monkeypatch.setattr(project, "preflight", lambda: None)
    def spawn(kind):
        identity = project.system.add(project, kind, 730 if kind == "model" else 731)
        project.created.append((kind, deepcopy(identity)))
        if kind == "ui":
            raise lifecycle.LifecycleError("initial UI startup failure")
        return project.inspect()
    monkeypatch.setattr(project, "spawn", spawn)
    original_terminate = project.system.terminate_exact
    def terminate(identity, timeout):
        if identity["pid"] == 731:
            raise lifecycle.LifecycleError("secondary termination denied")
        return original_terminate(identity, timeout)
    monkeypatch.setattr(project.system, "terminate_exact", terminate)
    with pytest.raises(lifecycle.LifecycleError, match="initial UI startup failure"):
        project.start()
    assert [p["pid"] for p in project.system.terminated] == [730]
    assert [p["pid"] for p in project.system.processes] == [731]
    assert any(event["event"] == "rollback_error" for event in project.events)


class FakeApi:
    def __init__(self, function):
        self.function = function

    def __call__(self, *args):
        return self.function(*args)


class FakeKernel:
    def __init__(self, created, exe):
        self.terminated_handles = []
        self.closed_handles = []
        self.OpenProcess = FakeApi(lambda *args: 12345)
        def times(handle, created_pointer, *unused):
            assert handle == 12345
            created_pointer._obj.dwLowDateTime = int(created) & 0xFFFFFFFF
            created_pointer._obj.dwHighDateTime = int(created) >> 32
            return 1
        self.GetProcessTimes = FakeApi(times)
        def image(handle, flags, output, length):
            output.value = exe
            return 1
        self.QueryFullProcessImageNameW = FakeApi(image)
        def terminate(handle, code):
            self.terminated_handles.append(handle)
            return 1
        self.TerminateProcess = FakeApi(terminate)
        self.WaitForSingleObject = FakeApi(lambda handle, timeout: 0 if self.terminated_handles else 258)
        self.CloseHandle = FakeApi(lambda handle: self.closed_handles.append(handle) or 1)


@pytest.mark.parametrize("identity_change", ["same_microsecond", "new_creation", "new_image"])
def test_native_termination_verifies_handle_identity_before_ending_same_handle(project, monkeypatch, identity_change):
    expected = project.system.add(project, "model", 710, created="133900000000000520")
    actual_created = "133900000000000526" if identity_change != "new_creation" else "133900000000000530"
    actual_exe = expected["exe"] if identity_change != "new_image" else str(project.root.parent / "other.exe")
    kernel = FakeKernel(actual_created, actual_exe)
    monkeypatch.setattr(lifecycle.ctypes, "WinDLL", lambda name, **kwargs: kernel)
    if identity_change == "same_microsecond":
        assert REAL_TERMINATE_EXACT(lifecycle.WindowsSystem(), expected, 1) == "terminated_and_waited"
        assert kernel.terminated_handles == [12345]
    else:
        with pytest.raises(lifecycle.LifecycleError, match="身份已变化"):
            REAL_TERMINATE_EXACT(lifecycle.WindowsSystem(), expected, 1)
        assert kernel.terminated_handles == []
    assert kernel.closed_handles == [12345]


@pytest.mark.parametrize("missing", [".venv/Scripts/python.exe", "models/test Q8_0.gguf", "runtime/bin/llama-server.exe", "scripts/serve_app.py", "frontend/dist/index.html"])
def test_preflight_missing_files_fails_without_subprocess_or_download(project, missing):
    (project.root / missing).unlink()
    with pytest.raises(lifecycle.LifecycleError, match="缺少必要文件") as error:
        project.preflight()
    assert missing in str(error.value)
    assert project.system.terminated == []


@pytest.mark.parametrize("missing", ["configs/launcher.json", "configs/model.json", "configs/model.lock.json"])
def test_missing_configuration_is_caught_before_any_process_action(project_root, missing):
    (project_root / missing).unlink()
    with pytest.raises(lifecycle.LifecycleError, match="配置无法读取"):
        lifecycle.Project(project_root, FakeSystem())


@pytest.mark.parametrize("endpoint", ["https://127.0.0.1:18080", "http://example.test:18080", "http://127.0.0.1", "http://user@127.0.0.1:18080"])
def test_nonlocal_or_ambiguous_endpoint_is_rejected_before_start(project_root, endpoint):
    path = project_root / "configs/model.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["endpoint"] = endpoint
    write_json(path, config)
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.Project(project_root, FakeSystem())


@pytest.mark.parametrize("key,value", [("temperature", 0.8), ("top_k", 1), ("min_p", 0.8), ("enable_thinking", True), ("server_parallel_slots", 2)])
def test_preflight_rejects_changed_frozen_model_conditions(project_root, key, value):
    path = project_root / "configs/model.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config[key] = value
    write_json(path, config)
    project = lifecycle.Project(project_root, FakeSystem())
    with pytest.raises(lifecycle.LifecycleError, match="不一致"):
        project.preflight()


def test_preflight_rejects_wrong_model_length(project):
    (project.root / project.lock["model_file"]).write_bytes(b"truncated")
    with pytest.raises(lifecycle.LifecycleError, match="模型文件长度不符"):
        project.preflight()


@pytest.mark.parametrize("problem", ["missing_fastapi", "missing_uvicorn", "missing_python_multipart", "missing_pypdf", "wrong_source", "old_python", "child_failure", "invalid_json"])
def test_preflight_dependency_errors_are_local_and_actionable(project, monkeypatch, problem):
    response = dependency_response(project)
    if problem.startswith("missing_"):
        response = dependency_response(project, missing=problem.removeprefix("missing_"))
    elif problem == "wrong_source":
        response = dependency_response(project, origin=project.root.parent / "another/src/taintlab/__init__.py")
    elif problem == "old_python":
        response = dependency_response(project, version=[3, 11])
    elif problem == "child_failure":
        response.returncode = 1
    else:
        response.stdout = b"not json"
    calls = []
    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return response
    monkeypatch.setattr(lifecycle.subprocess, "run", run)
    with pytest.raises(lifecycle.LifecycleError, match="install.ps1"):
        project.preflight()
    assert len(calls) == 1
    assert calls[0][0][0][0] == str(project.python)
    assert calls[0][0][0][1] == "-I"
    assert calls[0][1]["cwd"] == project.root
    assert project.system.terminated == []


def test_preflight_accepts_correct_isolated_environment_without_mutating_config(project, monkeypatch):
    before = {p.name: p.read_bytes() for p in (project.root / "configs").glob("*.json")}
    monkeypatch.setattr(lifecycle.subprocess, "run", lambda *args, **kwargs: dependency_response(project))
    project.preflight()
    assert before == {p.name: p.read_bytes() for p in (project.root / "configs").glob("*.json")}
    assert project.events[-1]["event"] == "preflight_passed"


@pytest.mark.parametrize("key,value", [("startup_timeout_seconds", None), ("startup_timeout_seconds", 0), ("startup_timeout_seconds", "not-a-number"), ("startup_timeout_seconds", float("nan")), ("stop_timeout_seconds", -1), ("operation_lock_timeout_seconds", float("inf"))])
def test_invalid_timeout_configuration_is_rejected_before_spawning(project_root, monkeypatch, key, value):
    path = project_root / "configs/launcher.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    if value is None:
        del config[key]
    else:
        config[key] = value
    write_json(path, config)
    # Either constructor or preflight may reject; both must precede spawn.
    with pytest.raises(lifecycle.LifecycleError):
        project = lifecycle.Project(project_root, FakeSystem())
        monkeypatch.setattr(lifecycle.subprocess, "run", lambda *args, **kwargs: dependency_response(project))
        project.preflight()


@pytest.mark.parametrize("port", [True, "18501", 18501.5, 0, 65536, 18080])
def test_invalid_or_shared_ui_port_rejected_before_process_actions(project_root, port):
    path = project_root / "configs/launcher.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    config["ui_port"] = port
    write_json(path, config)
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.Project(project_root, FakeSystem())


def test_model_spawn_uses_detached_handles_and_fixed_non_thinking_environment(project_root, monkeypatch):
    calls = []
    fake = SimpleNamespace(pid=801)
    def popen(*args, **kwargs):
        calls.append((args, kwargs))
        assert not kwargs["stdout"].closed and not kwargs["stderr"].closed
        return fake
    monkeypatch.setattr(model_launcher.subprocess, "Popen", popen)
    result = model_launcher.spawn_model(project_root, project_root / "logs", log_prefix="isolated")
    assert result is fake and len(calls) == 1
    args, kwargs = calls[0]
    assert kwargs["stdin"] == subprocess.DEVNULL and kwargs["close_fds"] is True
    assert kwargs["creationflags"] & subprocess.DETACHED_PROCESS
    assert kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
    assert kwargs["env"]["LLAMA_ARG_CHAT_TEMPLATE_KWARGS"] == '{"enable_thinking":false}'
    assert kwargs["cwd"] == Path(args[0][0]).parent
    assert kwargs["stdout"].closed and kwargs["stderr"].closed


def add_legacy_ui(project, pid=1701, *, base=False, parent_pid=None, listening=True):
    process = project.system.add(project, "ui", pid, listening=listening)
    process["argv"] = list(project.legacy_ui_command)
    if base:
        process["exe"] = str(project.base_python)
        process["argv"][0] = str(project.base_python)
    if parent_pid is not None:
        process["parent_pid"] = parent_pid
    return process


@pytest.mark.parametrize("base", [False, True])
def test_legacy_streamlit_requires_explicit_migration_without_spawn_or_termination(project, monkeypatch, base):
    project.system.add(project, "model", 1700)
    legacy = add_legacy_ui(project, base=base)
    monkeypatch.setattr(project, "preflight", lambda: None)
    with pytest.raises(lifecycle.LifecycleError, match="旧版 Streamlit"):
        project.start()
    ui = project.inspect()["ui"]
    assert ui["legacy_owned"] == [legacy] and not ui["healthy"]
    assert ui["service_variants"][str(legacy["pid"])] == "streamlit_v1"
    assert project.system.terminated == [] and project.created == [] and project.system.browsers == []
    assert ("ui", project.ports["ui"]) not in project.system.health_checks


def test_explicit_stop_safely_ends_legacy_server_redirector_then_model(project):
    project.system.add(project, "model", 1700)
    add_legacy_ui(project, 1701, listening=False)
    add_legacy_ui(project, 1702, base=True, parent_pid=1701)
    project.stop()
    assert [p["pid"] for p in project.system.terminated] == [1702, 1701, 1700]
    assert not project.system.processes


@pytest.mark.parametrize("mutation", ["foreign_source", "extra_arg", "wrong_port"])
def test_similar_foreign_streamlit_is_not_owned_or_terminated(project, mutation):
    process = add_legacy_ui(project)
    if mutation == "foreign_source":
        process["argv"][4] = str(project.root.parent / "other/app.py")
    elif mutation == "extra_arg":
        process["argv"].append("--server.enableCORS=false")
    else:
        process["argv"][process["argv"].index("--server.port") + 1] = "19501"
    assert not project.owned(process, "ui")
    project.stop()
    assert project.system.terminated == [] and project.system.processes == [process]


def test_different_ui_versions_cannot_form_a_redirector_child_identity_chain(project):
    add_legacy_ui(project, 1701, listening=False)
    child = project.system.add(project, "ui", 1702)
    child["parent_pid"] = 1701
    child["exe"] = str(project.base_python)
    child["argv"][0] = str(project.base_python)
    ui = project.inspect()["ui"]
    assert not ui["healthy"] and ui["launchers"] == []
    assert len(ui["owned"]) == 2


def test_v2_logs_are_isolated_from_all_old_launcher_evidence(project):
    legacy = project.root / "results/launcher/state.json"
    write_json(legacy, {"version": "1.0.0", "evidence": "preserve"})
    before = legacy.read_bytes()
    project.event("test")
    project.save_state(project.inspect())
    assert project.logs == project.root / "results/v2/launcher"
    assert json.loads(project.state_path.read_text(encoding="utf-8"))["version"] == "2.0.0"
    assert legacy.read_bytes() == before


@pytest.mark.parametrize("payload,status,expected", [
    ({"status": "ok", "service": "taintlab-web", "version": "2.0.0"}, 200, True),
    ({"status": "ok", "service": "other-app", "version": "2.0.0"}, 200, False),
    ({"status": "ok", "service": "taintlab-web", "version": "1.0.0"}, 200, False),
    ({"status": "ok"}, 200, False),
    ({"status": "ok", "service": "taintlab-web", "version": "2.0.0"}, 503, False),
    ([], 200, False),
    ("ok", 200, False),
])
def test_http_health_requires_new_api_identity_and_never_uses_system_proxy(monkeypatch, payload, status, expected):
    calls = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, bound):
            assert bound == 4096
            return json.dumps(payload).encode()
    response = Response()
    response.status = status
    class Opener:
        def open(self, url, timeout):
            calls.append((url, timeout))
            return response
    def opener(*handlers):
        assert handlers[0].proxies == {}
        with pytest.raises(ValueError, match="redirected"):
            handlers[1].redirect_request(None, None, None, None, None)
        return Opener()
    monkeypatch.setattr(lifecycle.urllib.request, "build_opener", opener)
    assert REAL_HTTP_HEALTH(lifecycle.WindowsSystem(), "ui", 18501) is expected
    assert calls == [("http://127.0.0.1:18501/api/health", 1.5)]


@pytest.mark.parametrize("reference", ["/assets/missing.js", "https://example.test/app.js", "//example.test/app.js", "../outside.js", "/%2e%2e/outside.js"])
def test_frontend_build_rejects_missing_remote_or_traversal_assets_before_process_actions(project, reference):
    entry = project.root / "frontend/dist/index.html"
    entry.write_text(f'<script src="{reference}"></script>', encoding="utf-8")
    with pytest.raises(lifecycle.LifecycleError, match="前端静态产物"):
        project.preflight()
    assert not project.created and not project.system.terminated


def test_frontend_build_checks_all_local_entry_assets_with_no_node_runtime_needed(project, monkeypatch):
    monkeypatch.setattr(lifecycle.subprocess, "run", lambda *args, **kwargs: dependency_response(project))
    project.preflight()
    event = project.events[-1]
    assert event["frontend_assets"] == ["assets/app.js", "assets/app.css"]
    assert event["ui_version"] == "2.0.0"
    assert event["ui_command"] == project.commands["ui"]
