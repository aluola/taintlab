"""Windows project lifecycle. Identity + listener ownership + HTTP health, never PID alone.

Only stdlib is required by this manager. It intentionally lives outside the frozen
Agent/evaluator. The exact old model/UI command lines are recognized during migration.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import unquote, urlparse
import urllib.request
import uuid

from launch_model import model_command, spawn_model

VERSION = "2.0.0"
WEB_SERVICE = "taintlab-web"
LOG_DIRECTORY = "results/v2/launcher"
ROOT = Path(__file__).resolve().parents[1]


class LifecycleError(RuntimeError):
    pass


class FrontendAssets(HTMLParser):
    """Read build entry references without executing JavaScript or fetching URLs."""

    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag == "script" and attributes.get("src"):
            self.references.append(attributes["src"])
        if tag == "link" and attributes.get("href") and set(attributes.get("rel", "").lower().split()) & {"stylesheet", "modulepreload", "preload", "icon", "manifest"}:
            self.references.append(attributes["href"])


def verify_frontend(root):
    directory = (Path(root) / "frontend/dist").resolve()
    entry = directory / "index.html"
    parser = FrontendAssets()
    parser.feed(entry.read_text(encoding="utf-8-sig"))
    if not parser.references:
        raise LifecycleError("frontend/dist/index.html 缺少可执行前端资源；请在 frontend 运行 npm ci 和 npm run build。")
    checked = []
    for reference in parser.references:
        url = urlparse(reference)
        if url.scheme or url.netloc or not url.path or "\\" in url.path:
            raise LifecycleError("前端静态产物引用了非本地资源或无效路径：" + reference)
        asset = (directory / unquote(url.path).lstrip("/")).resolve()
        if not asset.is_relative_to(directory) or not asset.is_file() or asset.stat().st_size == 0:
            raise LifecycleError("前端静态产物缺失或引用越界：" + reference + "；请在 frontend 运行 npm ci 和 npm run build。")
        checked.append(asset.relative_to(directory).as_posix())
    if not any(Path(name).suffix.lower() in {".js", ".mjs"} for name in checked):
        raise LifecycleError("frontend/dist 缺少 JavaScript 入口；请重新构建前端。")
    return checked


def norm(value):
    return os.path.normcase(os.path.abspath(str(value)))


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        if default is not None:
            return default
        raise LifecycleError(f"配置无法读取：{path}") from None


def split_command_line(command):
    if not command:
        return []
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    count = ctypes.c_int()
    pointer = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not pointer:
        return []
    try:
        return [pointer[i] for i in range(count.value)]
    finally:
        kernel.LocalFree(pointer)


def normalize_argv(argv):
    # All paths in managed commands are absolute, so no process cwd guess is needed.
    return [norm(s) if os.path.isabs(s) else s for s in argv]


def same_creation(first, second):
    return int(first) // 10 == int(second) // 10


def handle_identity(handle):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    times = [wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
        raise LifecycleError("无法核验原进程句柄创建时间")
    length = wintypes.DWORD(32768)
    image = ctypes.create_unicode_buffer(length.value)
    if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
        raise LifecycleError("无法核验原进程句柄可执行路径")
    return {"created": str((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime), "exe": image.value}


def powershell_json(script):
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    code = "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false);$ErrorActionPreference='Stop';" + script
    encoded = base64.b64encode(code.encode("utf-16-le")).decode("ascii")
    result = subprocess.run([str(executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                            capture_output=True, timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise LifecycleError("Windows进程/端口查询失败：" + result.stderr.decode("utf-8", errors="replace")[-1000:])
    return json.loads(result.stdout.decode("utf-8-sig"))


class WindowsSystem:
    def spawn_identity(self, process):
        # Popen retains the handle of the child it created; a reused PID cannot
        # substitute another process for this handle.
        return {"pid": process.pid, **handle_identity(process._handle)}

    def snapshot(self, ports):
        port_values = ",".join(str(int(p)) for p in ports)
        result = powershell_json("""
        $processes=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -in @('python.exe','pythonw.exe','llama-server.exe')} | ForEach-Object {
          [pscustomobject]@{pid=[int]$_.ProcessId; parent_pid=[int]$_.ParentProcessId; exe=$_.ExecutablePath; command_line=$_.CommandLine;
           created=if ($_.CreationDate) {$_.CreationDate.ToUniversalTime().ToFileTimeUtc().ToString()} else {''}}
        });
        $listeners=@(Get-NetTCPConnection -State Listen | Where-Object {$_.LocalPort -in @(""" + port_values + """)} | ForEach-Object {
          [pscustomobject]@{port=[int]$_.LocalPort; address=$_.LocalAddress; pid=[int]$_.OwningProcess}
        });
        [pscustomobject]@{processes=$processes;listeners=$listeners} | ConvertTo-Json -Depth 5 -Compress
        """)
        for process in result["processes"]:
            process["argv"] = split_command_line(process.pop("command_line") or "")
        return result

    def http_health(self, kind, port):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise ValueError("Health endpoint redirected")
        url = f"http://127.0.0.1:{port}" + ("/health" if kind == "model" else "/api/health")
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(url, timeout=1.5) as response:
                body = response.read(4096).decode("utf-8")
                payload = json.loads(body)
                return response.status == 200 and isinstance(payload, dict) and payload.get("status") == "ok" and (
                    kind == "model" or (payload.get("service") == WEB_SERVICE and payload.get("version") == VERSION))
        except (OSError, ValueError):
            return False

    def terminate_exact(self, process, timeout):
        """Open and verify a process handle, then terminate that handle (no PID race)."""
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000 | 0x100000 | 0x0001, False, process["pid"])
        if not handle:
            if ctypes.get_last_error() == 87:  # already gone
                return "already_exited"
            raise LifecycleError(f"无法安全打开进程 {process['pid']}，未结束任何未知进程")
        try:
            created, exited, kern, user = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kern), ctypes.byref(user)):
                raise LifecycleError("无法核验进程创建时间")
            actual_created = str((created.dwHighDateTime << 32) | created.dwLowDateTime)
            length = wintypes.DWORD(32768)
            image_path = ctypes.create_unicode_buffer(length.value)
            if not kernel.QueryFullProcessImageNameW(handle, 0, image_path, ctypes.byref(length)):
                raise LifecycleError("无法核验进程可执行文件")
            # Win32_Process CreationDate exposes microseconds, whereas FILETIME has
            # 100ns precision. Compare at the documented common precision.
            if not same_creation(actual_created, process["created"]) or norm(image_path.value) != norm(process["exe"]):
                raise LifecycleError(f"PID {process['pid']}身份已变化，拒绝终止")
            if kernel.WaitForSingleObject(handle, 0) == 0:
                return "already_exited"
            if not kernel.TerminateProcess(handle, 0):
                raise LifecycleError(f"进程 {process['pid']}终止失败")
            if kernel.WaitForSingleObject(handle, int(timeout * 1000)) != 0:
                raise LifecycleError(f"等待进程 {process['pid']}退出超时")
            return "terminated_and_waited"
        finally:
            kernel.CloseHandle(handle)

    def open_browser(self, url):
        # Windows ShellExecute is the same URL association used by Explorer.
        os.startfile(url)


@contextmanager
def project_mutex(root, timeout):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    name = "Local\\TaintLab_" + hashlib.sha256(norm(root).encode()).hexdigest()
    handle = kernel.CreateMutexW(None, False, name)
    if not handle:
        raise LifecycleError("无法创建项目操作锁")
    acquired = False
    try:
        acquired = kernel.WaitForSingleObject(handle, int(timeout * 1000)) in (0, 0x80)
        if not acquired:
            raise LifecycleError("另一个启动/关闭操作仍在进行，等待超时。请稍后再试。")
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


class Project:
    def __init__(self, root=ROOT, system=None):
        self.root = Path(root).resolve()
        self.system = system or WindowsSystem()
        self.settings = read_json(self.root / "configs/launcher.json")
        self.config = read_json(self.root / "configs/model.json")
        self.lock = read_json(self.root / "configs/model.lock.json")
        if not all(isinstance(value, dict) for value in (self.settings, self.config, self.lock)):
            raise LifecycleError("配置必须是JSON对象")
        for field in ("startup_timeout_seconds", "stop_timeout_seconds", "operation_lock_timeout_seconds"):
            value = self.settings.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= 300:
                raise LifecycleError(f"configs/launcher.json 的 {field} 必须是0至300之间的有限正数")
        if isinstance(self.settings.get("ui_port"), bool) or not isinstance(self.settings.get("ui_port"), int):
            raise LifecycleError("configs/launcher.json 的ui_port必须是整数")
        endpoint = urlparse(self.config["endpoint"])
        if endpoint.scheme != "http" or endpoint.hostname not in ("127.0.0.1", "localhost") or endpoint.username or not endpoint.port:
            raise LifecycleError("模型endpoint必须是显式端口的本机HTTP地址")
        self.ports = {"model": endpoint.port, "ui": int(self.settings["ui_port"])}
        if len(set(self.ports.values())) != 2 or not all(1 <= x <= 65535 for x in self.ports.values()):
            raise LifecycleError("模型与界面端口必须有效且互不相同")
        self.python = self.root / ".venv/Scripts/python.exe"
        self.base_python = Path(getattr(sys, "_base_executable", sys.executable)).resolve()
        self.commands = {
            "model": model_command(self.root),
            "ui": [str(self.python), str(self.root / "scripts/serve_app.py"),
                   "--host", "127.0.0.1", "--port", str(self.ports["ui"])],
        }
        # Legacy commands remain recognized for explicit stop/migration only.
        # A matching old Streamlit process never satisfies v2 UI health.
        self.legacy_ui_command = [str(self.python), "-m", "streamlit", "run", str(self.root / "src/taintlab/ui/app.py"),
                                  "--server.address", "127.0.0.1", "--server.port", str(self.ports["ui"]),
                                  "--server.headless", "true", "--browser.gatherUsageStats", "false"]
        self.logs = self.root / LOG_DIRECTORY
        self.logs.mkdir(parents=True, exist_ok=True)
        self.operation = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        self.events = []
        self.created = []
        self.state_path = self.logs / "state.json"

    def event(self, event, **data):
        item = {"time": datetime.now(timezone.utc).isoformat(), "operation": self.operation, "event": event, **data}
        self.events.append(item)
        with (self.logs / "operations.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")

    def process_variant(self, process, kind):
        commands = [("model" if kind == "model" else "web_v2", self.commands[kind])]
        if kind == "ui":
            commands.append(("streamlit_v1", self.legacy_ui_command))
            # The Windows venv redirector's child uses the base interpreter.
            commands += [(variant, [str(self.base_python), *command[1:]]) for variant, command in list(commands)]
        if process.get("created") and process.get("exe"):
            for variant, command in commands:
                if norm(process["exe"]) == norm(command[0]) and normalize_argv(process.get("argv", [])) == normalize_argv(command):
                    return variant
        return None

    def owned(self, process, kind):
        return self.process_variant(process, kind) is not None

    def inspect(self):
        snapshot = self.system.snapshot(self.ports.values())
        result = {}
        for kind, port in self.ports.items():
            candidates = [p for p in snapshot["processes"] if self.owned(p, kind)]
            launchers = [p for p in candidates if kind == "ui" and any(
                c.get("parent_pid") == p["pid"] and int(c["created"]) >= int(p["created"]) and
                self.process_variant(c, kind) == self.process_variant(p, kind) for c in candidates if c["pid"] != p["pid"])]
            launcher_ids = {p["pid"] for p in launchers}
            owned = [p for p in candidates if p["pid"] not in launcher_ids]
            listeners = [p for p in snapshot["listeners"] if p["port"] == port]
            ids = {p["pid"] for p in owned}
            conflicts = [p for p in listeners if p["pid"] not in ids]
            legacy_owned = [p for p in candidates if self.process_variant(p, kind) == "streamlit_v1"]
            healthy = (len(owned) == 1 and not legacy_owned and bool(listeners) and not conflicts and
                       all(p["pid"] == owned[0]["pid"] and p["address"] == "127.0.0.1" for p in listeners) and
                       self.system.http_health(kind, port))
            result[kind] = {"port": port, "owned": owned, "launchers": launchers, "listeners": listeners, "conflicts": conflicts,
                            "healthy": healthy, "legacy_owned": legacy_owned,
                            "service_variants": {str(p["pid"]): self.process_variant(p, kind) for p in candidates}}
        return result

    def inspect_hints(self, status):
        previous = read_json(self.state_path, {})
        services = previous.get("services", {}) if isinstance(previous, dict) else None
        if not isinstance(services, dict):
            self.event("invalid_state_hint", action="ignored_live_identity_remains_authoritative")
            services = {}
        for kind, saved in services.items():
            if kind not in self.commands or not isinstance(saved, dict):
                self.event("invalid_state_hint", service=str(kind), action="ignored_live_identity_remains_authoritative")
                continue
            same = [p for p in status.get(kind, {}).get("owned", []) if p["pid"] == saved.get("pid") and p["created"] == saved.get("created")]
            if not same:
                self.event("stale_or_mismatched_state", service=kind, pid=saved.get("pid"), action="hint_ignored_no_termination")
        for name, kind in (("results/environment/model.pid", "model"), ("results/ui.pid", "ui")):
            path = self.root / name
            if path.exists():
                try:
                    pid = int(path.read_text(encoding="utf-8-sig").strip())
                except (OSError, ValueError):
                    self.event("invalid_legacy_pid_hint", path=name)
                    continue
                if not any(p["pid"] == pid for p in status[kind]["owned"]):
                    self.event("stale_or_mismatched_legacy_pid", service=kind, pid=pid, action="hint_ignored_no_termination")

    def save_state(self, status):
        payload = {"version": VERSION, "project": str(self.root), "updated_at": datetime.now(timezone.utc).isoformat(),
                   "services": {kind: entry["owned"][0] for kind, entry in status.items() if len(entry["owned"]) == 1}}
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)

    def preflight(self):
        required = ["configs/model.json", "configs/model.lock.json", "configs/launcher.json", "scripts/launch_model.py",
                    "scripts/project_lifecycle.py", "scripts/start_model.ps1", "scripts/start_ui.ps1", "scripts/stop_model.ps1",
                    "scripts/serve_app.py", "frontend/dist/index.html", ".venv/Scripts/python.exe",
                    self.lock["model_file"], self.lock["server_file"]]
        missing = [name for name in required if not (self.root / name).is_file()]
        if missing:
            raise LifecycleError("缺少必要文件：\n  " + "\n  ".join(missing) +
                                 "\n修复：在项目根目录运行 powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install.ps1" +
                                 "\n模型准备：.venv\\Scripts\\python.exe scripts/model_prepare.py（仅首次需要下载）")
        frontend_assets = verify_frontend(self.root)
        checks = ("context_size", "max_tokens", "temperature", "top_p", "top_k", "min_p", "repeat_penalty")
        if any(self.config.get(k) != self.lock.get(k) for k in checks) or self.config.get("enable_thinking") is not False or self.lock.get("thinking") is not False:
            raise LifecycleError("模型配置与冻结锁定参数不一致；请核对configs/model.json和model.lock.json，不会静默替换配置")
        if self.config["server_parallel_slots"] != self.lock["parallel_slots"] or self.lock["server_context_size"] != self.config["context_size"] * self.lock["parallel_slots"]:
            raise LifecycleError("上下文或槽位配置不一致")
        if (self.root / self.lock["model_file"]).stat().st_size != self.lock["model_size_bytes"]:
            raise LifecycleError("模型文件长度不符；请运行 .venv\\Scripts\\python.exe scripts/model_prepare.py 校验并修复")
        code = "import importlib.util,json,sys; names=['fastapi','uvicorn','python_multipart','pypdf','pydantic','httpx','pandas','matplotlib','taintlab']; print(json.dumps({'version':list(sys.version_info[:2]),'modules':{n:(s.origin if (s:=importlib.util.find_spec(n)) else None) for n in names}}))"
        result = subprocess.run([str(self.python), "-I", "-c", code], cwd=self.root, capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            dependencies = json.loads(result.stdout)
        except ValueError:
            raise LifecycleError("虚拟环境不可运行；请使用scripts/install.ps1修复。") from None
        absent = [name for name, origin in dependencies["modules"].items() if origin is None]
        source = dependencies["modules"].get("taintlab")
        if result.returncode or absent or dependencies["version"] < [3, 12] or not source or norm(source) != norm(self.root / "src/taintlab/__init__.py"):
            raise LifecycleError(f"依赖缺失或环境绑定了其他目录：{absent or 'taintlab安装路径/Python版本'}；请运行scripts/install.ps1（不复制旧虚拟环境）")
        self.event("preflight_passed", python=str(self.python), ports=self.ports, model_command=self.commands["model"],
                   ui_command=self.commands["ui"], frontend_assets=frontend_assets, ui_version=VERSION)

    def spawn(self, kind):
        prefix = self.operation + "-" + kind
        if kind == "model":
            process = spawn_model(self.root, self.logs, log_prefix=prefix)
        else:
            with (self.logs / f"{prefix}.stdout.log").open("wb") as stdout, (self.logs / f"{prefix}.stderr.log").open("wb") as stderr:
                process = subprocess.Popen(self.commands[kind], cwd=self.root, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                           close_fds=True, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        self.event("spawn_requested", service=kind, pid=process.pid, stdout=f"{prefix}.stdout.log", stderr=f"{prefix}.stderr.log")
        origin = self.system.spawn_identity(process)
        if norm(origin["exe"]) != norm(self.commands[kind][0]):
            raise LifecycleError("新建进程句柄映像与预期不符，拒绝接管")
        # The original Popen handle and the command submitted by this manager
        # provide ownership even if a subsequent CIM query becomes unavailable.
        created_identity = {**origin, "argv": list(self.commands[kind])}
        self.created.append((kind, created_identity))
        deadline = time.monotonic() + float(self.settings["startup_timeout_seconds"])
        while time.monotonic() < deadline:
            status = self.inspect()
            if process.poll() is not None:
                raise LifecycleError(f"{kind}进程提前退出，exit={process.returncode}；日志：{self.logs / (prefix + '.stderr.log')}")
            identities = [p for p in status[kind]["owned"] + status[kind].get("launchers", []) if p["pid"] == process.pid and same_creation(p["created"], origin["created"])]
            if identities:
                for child in status[kind]["owned"]:
                    if child.get("parent_pid") == process.pid and int(child["created"]) >= int(origin["created"]) // 10 * 10 and not any(p["pid"] == child["pid"] and same_creation(p["created"], child["created"]) for _, p in self.created):
                        self.created.append((kind, child))
            if status[kind]["conflicts"]:
                raise LifecycleError(f"{kind}端口出现未知占用者，未结束该占用者")
            if status[kind]["healthy"] and identities:
                self.event("started_healthy", service=kind, identity=identities[0], port=self.ports[kind])
                return status
            if process.poll() is not None:
                raise LifecycleError(f"{kind}进程提前退出，exit={process.returncode}；日志：{self.logs / (prefix + '.stderr.log')}")
            time.sleep(0.35)
        raise LifecycleError(f"{kind}健康检查超时；日志：{self.logs / (prefix + '.stderr.log')}")

    def stop_identity(self, kind, identity, reason):
        try:
            current = self.inspect()
        except Exception:
            registered = any(k == kind and p["pid"] == identity["pid"] and same_creation(p["created"], identity["created"]) and
                             norm(p["exe"]) == norm(identity["exe"]) and normalize_argv(p["argv"]) == normalize_argv(identity["argv"])
                             for k, p in self.created)
            if reason != "rollback_only_created_by_this_operation" or not registered or not self.owned(identity, kind):
                raise
            # This fallback is available solely for the original native identity
            # of a child created in this operation, never for state/PID-file hints.
            outcome = self.system.terminate_exact(identity, float(self.settings["stop_timeout_seconds"]))
            self.event("process_stopped", service=kind, identity=identity, reason=reason, outcome=outcome, inspection="original_spawn_handle_identity_CIM_unavailable")
            return
        match = next((p for p in current[kind]["owned"] + current[kind].get("launchers", []) if p["pid"] == identity["pid"] and same_creation(p["created"], identity["created"])), None)
        if match is None:
            self.event("termination_skipped_identity_changed_or_exited", service=kind, pid=identity["pid"], reason=reason)
            return
        outcome = self.system.terminate_exact(match, float(self.settings["stop_timeout_seconds"]))
        self.event("process_stopped", service=kind, identity=match, reason=reason, outcome=outcome)

    def start(self, open_browser=True):
        self.preflight()
        status = self.inspect()
        self.inspect_hints(status)
        self.event("before_start", status=status)
        for kind, entry in status.items():
            if entry["conflicts"]:
                raise LifecycleError(f"端口冲突：{kind}的{entry['port']}端口由无法确认归属的PID {[x['pid'] for x in entry['conflicts']]}占用；不会自动结束。")
            if entry.get("legacy_owned"):
                self.event("legacy_ui_detected", identities=entry["legacy_owned"], action="explicit_stop_required_before_v2_start")
                raise LifecycleError("检测到本项目旧版 Streamlit 界面。请先双击关闭项目.cmd，再双击启动项目.cmd，迁移到 React/FastAPI 2.0.0；未自动替换旧进程。")
            if entry["owned"] and not entry["healthy"]:
                raise LifecycleError(f"本项目{kind}进程存在但不健康或重复。请双击关闭项目.cmd后再启动；日志：{self.logs}")
        try:
            for kind in ("model", "ui"):
                if status[kind]["healthy"]:
                    self.event("healthy_process_reused", service=kind, identity=status[kind]["owned"][0])
                else:
                    status = self.spawn(kind)
            status = self.inspect()
            if not all(entry["healthy"] for entry in status.values()):
                raise LifecycleError("最终身份/端口/健康复核失败")
            self.save_state(status)
            url = f"http://127.0.0.1:{self.ports['ui']}/"
            if open_browser:
                self.system.open_browser(url)
                self.event("browser_open_requested", url=url, mechanism="Windows ShellExecute URL association")
            self.event("start_complete", status=status)
            print(f"项目已启动，模型与界面均健康：{url}\n后台服务独立运行，可关闭启动窗口。\n日志：{self.logs}", flush=True)
            return status
        except Exception:
            for kind, identity in reversed(self.created):
                try:
                    self.stop_identity(kind, identity, "rollback_only_created_by_this_operation")
                except Exception as error:
                    self.event("rollback_error", service=kind, error=str(error))
            try:
                self.save_state(self.inspect())
            except Exception as error:
                self.event("rollback_state_refresh_failed", error=str(error))
            raise

    def stop(self):
        status = self.inspect()
        self.inspect_hints(status)
        self.event("before_stop", status=status)
        for kind in ("ui", "model"):
            for identity in status[kind]["owned"] + status[kind].get("launchers", []):
                self.stop_identity(kind, identity, "explicit_project_stop")
        after = self.inspect()
        self.save_state(after)
        if any(entry["owned"] for entry in after.values()):
            raise LifecycleError("本项目进程尚未全部退出，请查看生命周期日志")
        self.event("stop_complete", status=after)
        print("项目已停止。未删除模型、实验记录或其他项目数据。", flush=True)
        for kind, entry in after.items():
            if entry["conflicts"]:
                print(f"提示：{entry['port']}端口仍有非本项目进程，已保留，未终止。", flush=True)
        return after


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--no-browser", action="store_true", help="For automated tests or remote terminals only")
    parser.add_argument("--non-interactive", action="store_true", help="CMD wrapper skips error pause during automated validation")
    args = parser.parse_args()
    project = None
    try:
        if os.name != "nt":
            raise LifecycleError("此生命周期入口仅支持Windows；其他平台未验证")
        project = Project()
        with project_mutex(project.root, float(project.settings["operation_lock_timeout_seconds"])):
            if args.action == "start":
                status = project.start(not args.no_browser)
            elif args.action == "stop":
                status = project.stop()
            else:
                status = project.inspect()
                print(json.dumps(status, ensure_ascii=False, indent=2))
            record = {"version": VERSION, "operation": project.operation, "action": args.action, "success": True,
                      "status": status, "events": project.events}
            (project.logs / f"{project.operation}-{args.action}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except Exception as error:
        print(f"操作失败：{error}\n修复后可重新双击启动项目.cmd。", file=sys.stderr, flush=True)
        logs = project.logs if project else ROOT / LOG_DIRECTORY
        logs.mkdir(parents=True, exist_ok=True)
        if project:
            project.event("operation_failed", action=args.action, error=str(error))
        operation = project.operation if project else datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        (logs / f"{operation}-failed.json").write_text(json.dumps({"action": args.action, "success": False, "error": str(error), "events": project.events if project else []}, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
