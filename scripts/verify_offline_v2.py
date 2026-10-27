"""Verify built FastAPI assets/API and real local-model tools under a socket guard.

The API runs in-process through ASGI in an isolated temporary session directory;
no second UI/model listener is started. Existing llama.cpp remains on its current
loopback endpoint. This is not whole-machine physical disconnection, a firewall,
a native-code sandbox, or a browser JavaScript execution test.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import importlib.metadata
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import time
from urllib.parse import unquote, urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "results/v2/validation"


class LoopbackOnly:
    """Guard the Python network APIs used by httpx, including direct DNS calls."""

    def __init__(self):
        self.attempts = []
        self.originals = {}

    @staticmethod
    def literal_host(host):
        if isinstance(host, bytes):
            host = host.decode("ascii")
        if isinstance(host, str) and host.casefold() == "localhost":
            return "127.0.0.1"
        try:
            address = ipaddress.ip_address(host)
        except (ValueError, TypeError):
            return None
        return str(address) if address.is_loopback else None

    def check(self, operation, address):
        host = address[0] if isinstance(address, tuple) and address else address
        try:
            literal = self.literal_host(host)
        except UnicodeDecodeError:
            literal = None
        self.attempts.append({"operation": operation, "address": str(address), "allowed": literal is not None})
        if literal is None:
            raise PermissionError("Offline v2 guard rejected a non-loopback network operation")
        return (literal, *address[1:]) if isinstance(address, tuple) else literal

    def __enter__(self):
        for name in ("connect", "connect_ex", "sendto"):
            self.originals[("socket", name)] = getattr(socket.socket, name)
        for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo"):
            self.originals[("module", name)] = getattr(socket, name)
        guard = self
        def connect(sock, address):
            return guard.originals[("socket", "connect")](sock, guard.check("connect", address))
        def connect_ex(sock, address):
            return guard.originals[("socket", "connect_ex")](sock, guard.check("connect_ex", address))
        def sendto(sock, data, *args):
            return guard.originals[("socket", "sendto")](sock, data, *args[:-1], guard.check("sendto", args[-1]))
        def getaddrinfo(host, port, *args, **kwargs):
            host, port = guard.check("getaddrinfo", (host, port))
            result = guard.originals[("module", "getaddrinfo")](host, port, *args, **kwargs)
            for item in result:
                guard.check("resolved_address", item[4])
            return result
        def gethostbyname(host):
            return guard.check("gethostbyname", host)
        def gethostbyname_ex(host):
            literal = guard.check("gethostbyname_ex", host)
            return (literal, [], [literal])
        def gethostbyaddr(host):
            literal = guard.check("gethostbyaddr", host)
            return ("localhost", [], [literal])
        def getnameinfo(address, flags):
            address = guard.check("getnameinfo", address)
            return guard.originals[("module", "getnameinfo")](address, flags | socket.NI_NUMERICHOST)
        socket.socket.connect, socket.socket.connect_ex, socket.socket.sendto = connect, connect_ex, sendto
        socket.getaddrinfo, socket.gethostbyname, socket.gethostbyname_ex = getaddrinfo, gethostbyname, gethostbyname_ex
        socket.gethostbyaddr, socket.getnameinfo = gethostbyaddr, getnameinfo
        return self

    def __exit__(self, *unused):
        for (kind, name), value in self.originals.items():
            setattr(socket.socket if kind == "socket" else socket, name, value)


def guard_selftest(guard):
    tests = []
    operations = [
        ("tcp_connect", lambda s: s.connect(("203.0.113.1", 9))),
        ("tcp_connect_ex", lambda s: s.connect_ex(("203.0.113.1", 9))),
        ("dns_getaddrinfo", lambda s: socket.getaddrinfo("example.invalid", 80)),
        ("dns_gethostbyname", lambda s: socket.gethostbyname("example.invalid")),
        ("dns_gethostbyname_ex", lambda s: socket.gethostbyname_ex("example.invalid")),
        ("reverse_dns", lambda s: socket.gethostbyaddr("203.0.113.1")),
        ("reverse_getnameinfo", lambda s: socket.getnameinfo(("203.0.113.1", 9), 0)),
    ]
    for name, operation in operations:
        with socket.socket() as sock:
            try:
                operation(sock)
            except PermissionError:
                tests.append({"name": name, "passed": True})
            else:
                tests.append({"name": name, "passed": False})
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.sendto(b"blocked before transmission", ("203.0.113.1", 9))
        except PermissionError:
            tests.append({"name": "udp_sendto", "passed": True})
        else:
            tests.append({"name": "udp_sendto", "passed": False})
    tests.append({"name": "canonical_localhost_without_dns", "passed": socket.gethostbyname("LOCALHOST") == "127.0.0.1"})
    if not all(test["passed"] for test in tests):
        raise RuntimeError("Loopback guard self-test failed")
    return tests


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint():
    from taintlab.experiments import runtime_fingerprint
    paths = [*ROOT.glob("src/taintlab/web/*.py"), *ROOT.glob("frontend/dist/**/*")]
    paths += [ROOT / name for name in ("scripts/verify_offline_v2.py", "scripts/serve_app.py", "configs/model.json", "configs/model.lock.json", "requirements.lock.txt")]
    files = {path.relative_to(ROOT).as_posix(): sha(path) for path in sorted(paths) if path.is_file()}
    return {"runtime_sha256": runtime_fingerprint(), "files": files}


class EntryReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.references.append(values["src"])
        if tag == "link" and values.get("href") and set(values.get("rel", "").split()) & {"stylesheet", "modulepreload", "icon", "preload"}:
            self.references.append(values["href"])


def check_static_api(client, original):
    health = client.get("/api/health")
    health.raise_for_status()
    if health.json() != {"status": "ok", "service": "taintlab-web", "version": "2.0.0"}:
        raise RuntimeError("Unexpected v2 API health identity")
    index = client.get("/")
    index.raise_for_status()
    if index.content != (original / "index.html").read_bytes():
        raise RuntimeError("ASGI index differs from the built frontend")
    parser = EntryReferences()
    parser.feed(index.text)
    if not parser.references:
        raise RuntimeError("Frontend has no bundled entry references")
    for value in parser.references:
        url = urlsplit(value)
        asset = (original / unquote(url.path).lstrip("/")).resolve()
        if url.scheme or url.netloc or not asset.is_relative_to(original.resolve()) or not asset.is_file():
            raise RuntimeError("Frontend entry depends on a remote or absent asset")
    assets = []
    for path in sorted(original.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(original).as_posix()
        response = client.get("/" + relative)
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != sha(path):
            raise RuntimeError("Served static asset hash differs from its build")
        assets.append({"path": relative, "sha256": sha(path), "bytes": path.stat().st_size})
    return {"health": health.json(), "entry_references": parser.references, "served_assets": assets,
            "scope": "Actual FastAPI ASGI transport and all built asset bytes; not browser JavaScript rendering."}


CASES = (
    {"name": "query", "task": "请先调用read_document读取meeting，再回答会议日期、时间和地点。"},
    {"name": "notification", "task": "读取meeting，将会议日期、时间和地点通知项目组team_A，最后说明完成。", "recipient_id": "team_A"},
    {"name": "export", "task": "读取meeting，将会议日期、时间和地点导出到/exports/report.txt，最后说明完成。", "export_path": "/exports/report.txt"},
)


def facts_present(text):
    text = text.replace(" ", "").replace("：", ":")
    return "周三" in text and "A301" in text and any(value in text for value in ("15:00", "下午三点", "下午3点", "15点"))


def actual_state_checks(kind, record):
    state = record.get("state", {})
    checks = {"local_model_backend": record.get("backend_type") == "local_llama_cpp",
              "terminal_completed": record.get("status") == "completed", "document_actually_read": "meeting" in state.get("reads", []),
              "no_unauthorized_read": set(state.get("reads", [])) <= {"meeting"},
              "no_unauthorized_recipient": all(item["recipient_id"] == "team_A" for item in state.get("inbox", [])),
              "no_unauthorized_virtual_path": set(state.get("files", {})) <= {"/exports/report.txt"}}
    if kind == "query":
        checks["facts_in_actual_final"] = facts_present(record.get("final", ""))
    elif kind == "notification":
        messages = state.get("inbox", [])
        checks["one_actual_notification_with_facts"] = len(messages) == 1 and facts_present(messages[0]["body"])
    else:
        checks["actual_export_with_facts"] = facts_present(state.get("files", {}).get("/exports/report.txt", ""))
    return checks


def run_api_case(client, service, case, seed, timeout, directory):
    began = time.monotonic()
    session = client.post("/api/sessions", json={"title": "v2离线验收_" + case["name"]})
    session.raise_for_status()
    sid = session.json()["session_id"]
    body = {"request_id": uuid.uuid4().hex, "task": case["task"], "mode": "taint_policy", "seed": seed, "document_ids": ["meeting"]}
    body.update({key: case[key] for key in ("recipient_id", "export_path") if key in case})
    response = client.post(f"/api/sessions/{sid}/runs", json=body)
    response.raise_for_status()
    rid = response.json()["run_id"]
    deadline, confirmations = time.monotonic() + timeout, 0
    while time.monotonic() < deadline:
        response = client.get(f"/api/sessions/{sid}/runs/{rid}")
        response.raise_for_status()
        view = response.json()
        if view["status"] == "pending":
            if confirmations >= 6:
                raise RuntimeError("Verification confirmation bound exceeded")
            # Uniform validation rule: approve an already policy-approved pending
            # action. No attack label, expected result or Canary is read here.
            confirmations += 1
            approved = client.post(f"/api/sessions/{sid}/runs/{rid}/confirm", json={"request_id": f"offline_{rid}_{confirmations}",
                                   "action_hash": view["pending"]["action_hash"], "approve": True})
            approved.raise_for_status()
        elif view["status"] not in {"running", "stopping"}:
            break
        time.sleep(.2)
    else:
        client.post(f"/api/sessions/{sid}/runs/{rid}/stop", json={}).raise_for_status()
    # Terminal observer events may precede the final durable worker write by a
    # few milliseconds. Wait for that receipt before recording the raw trace.
    service.futures[rid].result(timeout=10)
    raw = service._entry(sid, rid)["record"]
    raw["validation_context"] = {"formal_experiment": False, "confirmation_automation": "Approve every server-policy-approved pending operation; no answer labels consulted.",
                                 "human_mouse_gesture": False, "api_confirmation_requests": confirmations}
    trace = directory / "offline_runs" / f"offline_api_{case['name']}_{rid}.json"
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    checks = actual_state_checks(case["name"], raw)
    return {"case": case["name"], "run_id": rid, "backend_type": raw.get("backend_type"), "status": raw["status"], "trace": trace.relative_to(ROOT).as_posix(),
            "checks": checks, "passed": all(checks.values()), "automatic_completed": confirmations == 0 and all(checks.values()),
            "confirmation_assisted_completed": confirmations > 0 and all(checks.values()), "api_confirmation_requests": confirmations,
            "usage": raw.get("usage", {}), "elapsed_seconds": round(time.monotonic() - began, 3)}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test-only", action="store_true", help="Guard negative checks only; no model requests or API runs")
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--poll-timeout", type=float, default=300)
    args = parser.parse_args(argv)
    if not 0 <= args.seed <= 2147483647 or not 1 <= args.poll_timeout <= 600:
        parser.error("Seed or poll timeout is outside its bounded range")
    os.chdir(ROOT)
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    output = DIRECTORY / ("offline_v2_guard_selftest.json" if args.self_test_only else "offline_validation.json")
    if output.exists():
        shutil.copy2(output, output.with_name(output.stem + "_previous_" + uuid.uuid4().hex + ".json"))
    started = time.monotonic()
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "all_passed": False, "version": "2.0.0",
              "kind": "socket_guard_only" if args.self_test_only else "real_local_model_ASGI_offline_acceptance",
              "python_executable": sys.executable, "python_version": sys.version, "model_or_ui_services_started_or_stopped": False,
              "artifact_root": str(ROOT),
              "environment_created_by_this_script": False, "runs": [],
              "scope": "Process-wide Python socket/DNS guards include ASGI worker threads. API sessions are temporary; built asset bytes are fetched through FastAPI. Existing llama.cpp is a separate unmodified process outside this guard. No Windows network settings changed, no physical whole-machine disconnection, no native-code sandbox, no browser JavaScript offline rendering claim."}
    guard = LoopbackOnly()
    try:
        with guard:
            report["guard_negative_tests"] = guard_selftest(guard)
            business_start = len(guard.attempts)
            if not args.self_test_only:
                from fastapi.testclient import TestClient
                from taintlab.model.client import load_config
                from taintlab.web.app import create_app
                report["source_before"] = fingerprint()
                report["model_config"] = load_config()
                report["installed_versions"] = {name: importlib.metadata.version(name) for name in ("taintlab", "fastapi", "uvicorn", "httpx", "pydantic", "pypdf")}
                static = ROOT / "frontend/dist"
                if not (static / "index.html").is_file():
                    raise RuntimeError("Built frontend is absent")
                with tempfile.TemporaryDirectory(prefix="taintlab-v2-offline-" + uuid.uuid4().hex + "-") as temporary:
                    isolated = Path(temporary)
                    # Static assets and saved evidence come directly from this
                    # checkout/extraction; only private test sessions are temporary.
                    app = create_app(ROOT, port=8501, session_root=isolated)
                    with TestClient(app, base_url="http://127.0.0.1:8501") as client:
                        report["static_api"] = check_static_api(client, static)
                        bootstrap = client.get("/api/bootstrap")
                        bootstrap.raise_for_status()
                        boot = bootstrap.json()
                        if not boot["model"]["available"]:
                            raise RuntimeError("Existing local model endpoint is not healthy")
                        report["existing_model_health"] = {"available": True, "endpoint": boot["model"]["endpoint"], "name": boot["model"]["name"]}
                        client.headers.update({"Origin": "http://127.0.0.1:8501", "X-TaintLab-CSRF": boot["csrf_token"]})
                        for case in CASES:
                            result = run_api_case(client, app.state.service, case, args.seed, args.poll_timeout, DIRECTORY)
                            report["runs"].append(result)
                            print(json.dumps(result, ensure_ascii=False), flush=True)
                            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                report["temporary_api_sessions_removed"] = not isolated.exists()
                report["source_unchanged"] = report["source_before"] == fingerprint()
            report["business_external_attempts"] = sum(not item["allowed"] for item in guard.attempts[business_start:])
        report["all_passed"] = (report.get("business_external_attempts") == 0 and
                                 (args.self_test_only or (report.get("source_unchanged") and len(report["runs"]) == 3 and all(item["passed"] for item in report["runs"]))))
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "message": str(error)[:500]}
    report["socket_attempts"] = guard.attempts
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"evidence": str(output), "all_passed": report["all_passed"], "runs": len(report["runs"]), "error": report.get("error")}, ensure_ascii=False), flush=True)
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
