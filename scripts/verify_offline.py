"""Run true local-model acceptance with non-loopback Python sockets disabled.

This is process-scoped validation, not a Windows firewall or a physical air gap.
It does not alter the user's network settings or restart the llama.cpp service.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import importlib.metadata
import json
from pathlib import Path
import secrets
import socket
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


class LoopbackOnly:
    """Reject DNS and Python socket connections except explicit loopback targets."""

    def __init__(self):
        self.attempts = []
        self.originals = {}

    def allow_host(self, host):
        if isinstance(host, bytes):
            host = host.decode("ascii")
        if isinstance(host, str) and host.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def check(self, operation, address):
        host = address[0] if isinstance(address, tuple) and address else address
        allowed = self.allow_host(host)
        self.attempts.append({"operation":operation,"address":str(address),"allowed":allowed})
        if not allowed:
            raise PermissionError(f"Offline verification blocked non-loopback {operation}")

    @staticmethod
    def literal_address(address):
        if isinstance(address,tuple) and address and address[0] in ("localhost",b"localhost"):
            return ("127.0.0.1",*address[1:])
        return address

    def __enter__(self):
        self.originals = {"connect":socket.socket.connect,"connect_ex":socket.socket.connect_ex,"sendto":socket.socket.sendto,"getaddrinfo":socket.getaddrinfo}
        guard = self
        def connect(sock, address):
            guard.check("connect",address)
            return guard.originals["connect"](sock,guard.literal_address(address))
        def connect_ex(sock,address):
            guard.check("connect_ex",address)
            return guard.originals["connect_ex"](sock,guard.literal_address(address))
        def sendto(sock,data,*args):
            guard.check("sendto",args[-1])
            return guard.originals["sendto"](sock,data,*args[:-1],guard.literal_address(args[-1]))
        def getaddrinfo(host,port,*args,**kwargs):
            guard.check("getaddrinfo",(host,port))
            # Do not consult external DNS even for the special localhost spelling.
            if host in ("localhost",b"localhost"):
                host="127.0.0.1"
            answers=guard.originals["getaddrinfo"](host,port,*args,**kwargs)
            for answer in answers:
                guard.check("resolved_address",answer[4])
            return answers
        socket.socket.connect=connect
        socket.socket.connect_ex=connect_ex
        socket.socket.sendto=sendto
        socket.getaddrinfo=getaddrinfo
        return self

    def __exit__(self,*_):
        socket.socket.connect=self.originals["connect"]
        socket.socket.connect_ex=self.originals["connect_ex"]
        socket.socket.sendto=self.originals["sendto"]
        socket.getaddrinfo=self.originals["getaddrinfo"]


def guard_selftest():
    tests=[]
    operations = [
        ("tcp_connect",lambda s:s.connect(("203.0.113.1",9))),
        ("tcp_connect_ex",lambda s:s.connect_ex(("203.0.113.1",9))),
        ("dns",lambda s:socket.getaddrinfo("example.invalid",80)),
    ]
    for name, operation in operations:
        with socket.socket() as sock:
            try:
                operation(sock)
            except PermissionError:
                tests.append({"name":name,"passed":True})
            else:
                tests.append({"name":name,"passed":False})
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        try:
            sock.sendto(b"guard selftest",("203.0.113.1",9))
        except PermissionError:
            tests.append({"name":"udp_sendto","passed":True})
        else:
            tests.append({"name":"udp_sendto","passed":False})
    if not all(test["passed"] for test in tests):
        raise AssertionError("Socket guard failed its negative checks")
    return tests


def fingerprints():
    paths=list((ROOT/"src").rglob("*.py"))
    paths += [ROOT/p for p in ("requirements.lock.txt","pyproject.toml","configs/model.json","configs/model.lock.json","data/dev.jsonl","data/test.jsonl","data/frozen_manifest.json","scripts/verify_offline.py","scripts/install.ps1")]
    hashes={str(p.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}
    aggregate=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    return {"aggregate_sha256":aggregate,"files":hashes}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test-only",action="store_true")
    parser.add_argument("--seed",type=int,default=11)
    parser.add_argument("--cases",nargs="+",default=["dev_normal_query_1","dev_normal_notification_1","dev_normal_export_1"])
    parser.add_argument("--mode",default="taint_policy",choices=["none","input_filter","taint_policy","policy_only"])
    args=parser.parse_args()
    directory=ROOT/"results/validation"
    directory.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    result={"started_at_utc":datetime.now(timezone.utc).isoformat(),"python_executable":sys.executable,"python_version":sys.version,"installed_versions":{d.metadata["Name"]:d.version for d in importlib.metadata.distributions()},"scope":"New virtual environment with cached offline dependencies; non-loopback Python socket APIs blocked in application process. Not physical whole-machine disconnection; existing llama.cpp process is outside the monkeypatch. This guard covers standard Python socket APIs used by httpx; it does not constrain malicious native code or spawned processes.","mode":args.mode,"seed":args.seed,"source_fingerprints":fingerprints(),"runs":[]}
    with LoopbackOnly() as guard:
        result["guard_negative_tests"]=guard_selftest()
        validation_start=len(guard.attempts)
        # Imports occur after the guard, so import-time network access is also blocked.
        import httpx
        with httpx.Client(trust_env=False,follow_redirects=False,timeout=15) as client:
            health=client.get("http://127.0.0.1:8080/health")
            health.raise_for_status()
            result["model_health"]=health.json()
        if not args.self_test_only:
            from taintlab.agent.runtime import run_case
            from taintlab.evaluation.evaluator import evaluate
            from taintlab.experiments import runtime_fingerprint
            from taintlab.model.client import load_config
            result["runtime_fingerprint"]=runtime_fingerprint()
            result["model_config"]=load_config()
            frozen_manifest=ROOT/"data/frozen_manifest.json"
            result["frozen_dataset_manifest"]=json.loads(frozen_manifest.read_text(encoding="utf-8")) if frozen_manifest.exists() else None
            cases=[json.loads(line) for line in (ROOT/"data/dev.jsonl").read_text(encoding="utf-8-sig").splitlines() if line.strip()]
            for case_id in args.cases:
                case=next(c for c in cases if c["id"]==case_id)
                canary="CANARY_"+secrets.token_hex(16)
                record=run_case(case["runtime"],args.mode,args.seed,run_id="offline_"+uuid.uuid4().hex,canary=canary,confirmation_mode="pending")
                assessment=evaluate(case,record,canary)
                record.update(case_id=case_id,kind=case["kind"],category=case["category"],assessment=assessment)
                record_path=directory/("offline_"+case_id+"_"+record["run_id"]+".json")
                record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
                result["runs"].append({"case_id":case_id,"run_id":record["run_id"],"backend_type":record["backend_type"],"status":record["status"],"assessment":assessment,"trace":str(record_path.relative_to(ROOT)).replace("\\","/")})
                print(json.dumps(result["runs"][-1],ensure_ascii=False),flush=True)
        result["socket_attempts"]=guard.attempts
        result["business_external_attempts"]=sum(not a["allowed"] for a in guard.attempts[validation_start:])
    result["elapsed_seconds"]=round(time.perf_counter()-started,4)
    result["source_unchanged_during_verification"]=result["source_fingerprints"]==fingerprints()
    result["verification_kind"]="socket_guard_selftest" if args.self_test_only else "true_local_model_acceptance"
    result["all_completed"]=all(r["status"]=="completed" for r in result["runs"]) if result["runs"] else None
    result["all_tasks_succeeded"]=all(r["status"]=="completed" and r["backend_type"]=="local_llama_cpp" and r["assessment"].get("legitimate_success") and not r["assessment"].get("any_violation") for r in result["runs"]) if result["runs"] else None
    output=directory/("offline_guard_selftest.json" if args.self_test_only else "offline_validation.json")
    if output.exists() and not args.self_test_only:
        previous=json.loads(output.read_text(encoding="utf-8"))
        archive=directory/("offline_validation_previous_"+uuid.uuid4().hex+".json")
        archive.write_text(json.dumps(previous,ensure_ascii=False,indent=2),encoding="utf-8")
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"evidence":str(output),"run_count":len(result["runs"]),"all_completed":result["all_completed"],"all_tasks_succeeded":result["all_tasks_succeeded"],"business_external_attempts":result["business_external_attempts"],"source_unchanged":result["source_unchanged_during_verification"]},ensure_ascii=False,indent=2))
    if not result["source_unchanged_during_verification"] or result["business_external_attempts"]:
        raise SystemExit(1)
    if result["runs"] and not result["all_tasks_succeeded"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
