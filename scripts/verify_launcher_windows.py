"""Explicit Windows integration acceptance: changes only this project's services.

Run with --execute. Uses ShellExecuteEx on the actual CMD files, the same Windows
file association entry point as Explorer double-click, not a claimed human click.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

from project_lifecycle import LOG_DIRECTORY, Project, ROOT, VERSION

VALIDATION_DIRECTORY = LOG_DIRECTORY + "/validation"
FORMAL_DIRECTORIES = ("results/main", "results/ablation", "results/v2/baseline", "results/v2/external")


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG), ("hwnd", wintypes.HWND),
                ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]


def activate_cmd(action, no_browser=True):
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x00000040 | 0x00000100  # NOCLOSEPROCESS | NOASYNC
    info.lpVerb = "open"
    info.lpFile = str(ROOT / ("启动项目.cmd" if action == "start" else "关闭项目.cmd"))
    info.lpParameters = "--non-interactive" + (" --no-browser" if no_browser else "")
    info.lpDirectory = os.environ.get("SystemRoot", r"C:\Windows")  # intentionally unrelated cwd
    info.nShow = 0  # Automated acceptance is hidden; this is not a human gesture.
    began = time.monotonic()
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if kernel.WaitForSingleObject(info.hProcess, 180000) != 0:
            raise RuntimeError("CMD launcher did not exit within 180 seconds")
        code = wintypes.DWORD()
        assert kernel.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
        return {"action": action, "exit_code": code.value, "launcher_exited": True,
                "elapsed_seconds": round(time.monotonic() - began, 3), "entry": info.lpFile,
                "activation": "Windows ShellExecuteEx file association", "cwd": info.lpDirectory,
                "browser_requested": not no_browser, "window_visibility": "hidden_automated_acceptance"}
    finally:
        kernel.CloseHandle(info.hProcess)


def service_ids(status):
    return {kind: [(p["pid"], p["created"]) for p in entry["owned"]] for kind, entry in status.items()}


def protected_files(root=ROOT):
    root = Path(root)
    files = {p for p in (root / "data").rglob("*") if p.is_file() and p.suffix not in {".tmp", ".pyc"}}
    for directory in FORMAL_DIRECTORIES:
        folder = root / directory
        files.update((folder / "records").glob("*.json"))
        files.update(p for p in folder.glob("*") if p.is_file() and p.name in {
            "experiment_manifest.json", "metrics.jsonl", "metrics.csv", "summary.json", "paired_scenarios.json", "checkpoints.sqlite"})
    for directory in ("results/validation", "results/launcher/validation"):
        files.update(p for p in (root / directory).rglob("*") if p.is_file())
    lock = root / "configs/experiment_v2.lock.json"
    if lock.is_file():
        files.add(lock)
    return sorted(files)


def protected_hash(root=ROOT):
    root = Path(root)
    files = protected_files(root)
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.relative_to(root).as_posix().encode())
        digest.update(file.read_bytes())
    return {"files": len(files), "sha256": digest.hexdigest(),
            "formal_records": {directory: len(list((root / directory / "records").glob("*.json"))) for directory in FORMAL_DIRECTORIES}}


def verify_frozen_campaigns(root=ROOT):
    """Fail before process operations while a frozen v2 batch is incomplete."""
    root = Path(root)
    lock_path = root / "configs/experiment_v2.lock.json"
    if not lock_path.is_file():
        raise RuntimeError("缺少 v2 实验冻结锁；真实启停验收需在正式批次完成后运行。")
    signature = json.loads(lock_path.read_text(encoding="utf-8"))["signature"]
    planned = signature["planned_runs"]
    if set(planned) != {"baseline", "external"} or any(not isinstance(n, int) or n <= 0 for n in planned.values()):
        raise RuntimeError("v2 冻结批次配置无效，未操作任何服务。")
    result = {}
    for name, expected in planned.items():
        folder = root / "results/v2" / name
        required = [folder / file for file in ("experiment_manifest.json", "metrics.jsonl", "summary.json")]
        count = len(list((folder / "records").glob("*.json")))
        if count != expected or not all(path.is_file() for path in required):
            raise RuntimeError(f"v2 {name} 尚未完成（{count}/{expected}）；未启动或停止服务，请先完成正式批次。")
        manifest = json.loads(required[0].read_text(encoding="utf-8"))
        metric_count = sum(1 for line in required[1].read_text(encoding="utf-8").splitlines() if line.strip())
        if (manifest.get("planned_runs") != expected or metric_count != expected or
                manifest.get("runtime_sha256") != signature["runtime_sha256"] or manifest.get("backend_type") != "local_llama_cpp"):
            raise RuntimeError(f"v2 {name} 与冻结批次不一致；未操作任何服务。")
        result[name] = {"planned": expected, "records": count, "metrics": metric_count, "runtime_sha256": manifest["runtime_sha256"]}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute:
        parser.error("Pass --execute to perform the documented real service lifecycle")
    if os.name != "nt":
        parser.error("此真实启停验收只支持 Windows。")
    # This gate deliberately precedes Project construction, snapshots and CMDs.
    campaign_state = verify_frozen_campaigns(ROOT)
    folder = ROOT / VALIDATION_DIRECTORY
    folder.mkdir(parents=True, exist_ok=True)
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "kind": "actual_windows_CMD_lifecycle", "version": VERSION,
              "activation_method": "ShellExecuteEx on actual root CMD files; equivalent Windows file association to double-click; no human mouse gesture claimed",
              "checks": {}, "steps": [], "all_passed": False, "completed_v2_campaigns": campaign_state, "protected_before": protected_hash(ROOT)}
    project = Project()
    project.preflight()
    def record(name, passed, detail=None):
        report["checks"][name] = bool(passed)
        report["steps"].append({"name": name, "passed": bool(passed), "detail": detail})
        (folder / "actual_windows_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(name, "PASS" if passed else "FAIL", flush=True)
        assert passed, name
    initial = project.inspect()
    report["initial"] = initial
    record("initial_ports_have_no_unknown_owners", all(not value["conflicts"] for value in initial.values()), initial)
    record("initial_model_absent_or_verified_healthy", not initial["model"]["owned"] or initial["model"]["healthy"], initial["model"])
    if initial["ui"].get("legacy_owned"):
        step = activate_cmd("start")
        record("legacy_Streamlit_requires_explicit_stop", step["exit_code"] != 0 and service_ids(project.inspect()) == service_ids(initial), step)
        report["legacy_migration"] = {"tested": True, "source": "preexisting_verified_Streamlit"}
    else:
        report["legacy_migration"] = {"tested": False, "reason": "No preexisting legacy process; isolated migration regressions cover this branch."}
    step = activate_cmd("stop")
    state = project.inspect()
    record("initial_services_closed_by_v2_CMD", step["exit_code"] == 0 and all(not s["owned"] for s in state.values()), {"entry": step, "status": state})
    # Prove the migrated foreground PowerShell entry starts the actual v2 API.
    foreground = None
    if not state["ui"]["owned"] and not state["ui"]["listeners"]:
        ps = str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
        with (folder / "foreground_v2_ui.stdout.log").open("wb") as stdout, (folder / "foreground_v2_ui.stderr.log").open("wb") as stderr:
            foreground = subprocess.Popen([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/start_ui.ps1"), "-Port", str(project.ports["ui"])],
                                      cwd=os.environ["SystemRoot"], stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            state = project.inspect()
            if state["ui"]["healthy"]:
                break
            if foreground.poll() is not None:
                raise RuntimeError("v2 UI launch failed; inspect validation/foreground_v2_ui.stderr.log")
            time.sleep(.5)
        record("foreground_start_ui_uses_verified_v2_API", state["ui"]["healthy"] and not state["ui"]["legacy_owned"] and
               set(state["ui"]["service_variants"].values()) == {"web_v2"}, state["ui"])
    step = activate_cmd("stop")
    state = project.inspect()
    record("foreground_v2_UI_closed_by_CMD", step["exit_code"] == 0 and all(not s["owned"] for s in state.values()), {"entry": step, "status": state})
    if foreground is not None:
        foreground.wait(timeout=15)
    # Cold start via actual file association, including browser launch.
    step = activate_cmd("start", no_browser=False)
    state = project.inspect()
    record("cold_CMD_start_from_unrelated_cwd", step["exit_code"] == 0 and all(s["healthy"] for s in state.values()), {"entry": step, "status": state})
    before_ids = service_ids(state)
    time.sleep(2)
    after = project.inspect()
    record("services_survive_launcher_exit", all(s["healthy"] for s in after.values()) and service_ids(after) == before_ids, after)
    step = activate_cmd("start")
    after = project.inspect()
    record("sequential_start_reuses_processes", step["exit_code"] == 0 and service_ids(after) == before_ids, {"entry": step, "status": after})
    with ThreadPoolExecutor(max_workers=2) as pool:
        simultaneous = list(pool.map(lambda _: activate_cmd("start"), range(2)))
    after = project.inspect()
    record("concurrent_start_no_duplicates", all(s["exit_code"] == 0 for s in simultaneous) and service_ids(after) == before_ids, {"entries": simultaneous, "status": after})
    step = activate_cmd("stop")
    after = project.inspect()
    record("CMD_stop_both_exit", step["exit_code"] == 0 and all(not s["owned"] and not s["listeners"] for s in after.values()), {"entry": step, "status": after})
    record("repeated_stop_is_success", activate_cmd("stop")["exit_code"] == 0)
    # Unrelated real listeners deliberately have the same Python exe but different argv.
    for kind, port in project.ports.items():
        foreign = subprocess.Popen([str(project.base_python), "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                                   cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=1):
                        break
                except OSError:
                    time.sleep(.2)
            step = activate_cmd("start")
            record(f"{kind}_foreign_port_rejected_without_kill", step["exit_code"] != 0 and foreign.poll() is None and all(not s["owned"] for s in project.inspect().values()), {"foreign_test_pid": foreign.pid, "entry": step})
            step = activate_cmd("stop")
            record(f"{kind}_foreign_listener_survives_stop", step["exit_code"] == 0 and foreign.poll() is None, step)
        finally:
            # This is the harness's own Popen handle, never a PID/port-based kill.
            foreign.terminate()
            foreign.wait(timeout=10)
    # Missing environment: copy only CMD to a new isolated Chinese/space directory.
    fixture = folder / ("缺失环境 中文 space " + datetime.now().strftime("%Y%m%dT%H%M%S_%f"))
    fixture.mkdir()
    shutil.copy2(ROOT / "启动项目.cmd", fixture / "启动项目.cmd")
    command = f'"{os.environ["COMSPEC"]}" /d /s /c ""{fixture / "启动项目.cmd"}" --non-interactive"'
    missing = subprocess.run(command, cwd=os.environ["SystemRoot"], capture_output=True, timeout=15)
    output = (missing.stdout + missing.stderr).decode("utf-8", errors="replace")
    record("missing_venv_message_and_nonzero_exit", missing.returncode != 0 and "缺少项目虚拟环境" in output and "install.ps1" in output, {"exit_code": missing.returncode, "output": output, "isolated_fixture": str(fixture)})
    step = activate_cmd("start", no_browser=False)
    final = project.inspect()
    record("restart_and_leave_healthy", step["exit_code"] == 0 and all(s["healthy"] for s in final.values()), {"entry": step, "status": final})
    report["final"] = final
    report["protected_after"] = protected_hash(ROOT)
    record("frozen_data_and_all_v1_v2_records_unchanged", report["protected_before"] == report["protected_after"])
    report["all_passed"] = all(report["checks"].values())
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    (folder / "actual_windows_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"all_passed": report["all_passed"], "checks": len(report["checks"]), "url": f"http://127.0.0.1:{project.ports['ui']}/"}), flush=True)


if __name__ == "__main__":
    main()
