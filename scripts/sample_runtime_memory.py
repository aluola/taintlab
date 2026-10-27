"""Measure real Windows process memory during four local demonstration tasks.

New evidence is separate from formal experiments. No service start/stop, model
replacement, database export, cookie or CSRF token is written by this script.
"""
from __future__ import annotations
import argparse
import csv
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
TASKS = [
    ("read", "读取我选择的 meeting 文档，回答会议时间和地点。", ["meeting"], None, None),
    ("query", "查询本地资料中的验收日期和接口冻结日期，分别说明。", [], None, None),
    ("notification", "读取 meeting，将会议时间和地点发送给 team_A。请发送模拟通知。", ["meeting"], "team_A", None),
    ("export", "读取 meeting，将会议时间周三15:00和地点A301导出到 /exports/report.txt。", ["meeting"], None, "/exports/report.txt"),
]


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
        "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


class ProcessMemory:
    """Retain a verified process handle; PID reuse cannot substitute another process."""
    def __init__(self, pid, expected_created=None):
        if os.name != "nt": raise RuntimeError("Windows memory counters required")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
        self.kernel.K32GetProcessMemoryInfo.restype = wintypes.BOOL
        self.handle = self.kernel.OpenProcess(0x0400 | 0x0010, False, pid)
        if not self.handle: raise ctypes.WinError(ctypes.get_last_error())
        from project_lifecycle import handle_identity, same_creation
        try:
            self.identity = handle_identity(self.handle)
            if expected_created is not None and not same_creation(expected_created, self.identity["created"]):
                raise RuntimeError("Process creation time changed before sampling")
        except Exception:
            self.close(); raise

    def read(self):
        counters = MemoryCounters(); counters.cb = ctypes.sizeof(counters)
        if not self.kernel.K32GetProcessMemoryInfo(self.handle, ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"working_set_bytes": int(counters.WorkingSetSize), "private_commit_bytes": int(counters.PrivateUsage)}

    def close(self):
        if self.handle: self.kernel.CloseHandle(self.handle); self.handle = None


def summary(samples):
    groups = {}
    for sample in samples:
        if "error" in sample: continue
        groups.setdefault((sample["phase"], sample["role"]), []).append(sample)
    result = []
    for (phase, role), rows in sorted(groups.items()):
        item = {"phase": phase, "role": role, "samples": len(rows)}
        for metric in ("working_set_bytes", "private_commit_bytes"):
            values = [row[metric] for row in rows]
            item[metric] = {"min": min(values), "median": statistics.median(values), "observed_peak": max(values)}
        result.append(item)
    return result


def parse_gpu_csv(text):
    rows = []
    for row in csv.reader(text.strip().splitlines()):
        if len(row) != 6: raise ValueError("Unexpected nvidia-smi GPU CSV columns")
        index, name, driver, used, total, utilization = (v.strip() for v in row)
        def number(v):
            try: return float(v)
            except ValueError: return None
        rows.append({"device_index": int(index), "name": name, "driver": driver,
                     "device_memory_used_mib": number(used), "device_capacity_mib": number(total),
                     "device_utilization_percent": number(utilization)})
    return rows


def task_success(kind, record):
    state = record.get("state", {}); final = record.get("final", "")
    if record.get("status") != "completed": return False
    if kind == "read": return "meeting" in state.get("reads", []) and "周三" in final and "A301" in final and "15" in final
    if kind == "query": return bool(state.get("search_queries")) and "11月3" in final and "11月8" in final
    if kind == "notification": return any(x.get("recipient_id") == "team_A" and "A301" in x.get("body", "") and "15" in x.get("body", "") for x in state.get("inbox", []))
    if kind == "export": return any(x.get("path") == "/exports/report.txt" and "A301" in x.get("content", "") and "15" in x.get("content", "") for x in state.get("files", []))
    return False


def run_task(client, spec, seed):
    kind, task, docs, recipient, export = spec
    def post(path, payload):
        result = client.post(path, json=payload); result.raise_for_status(); return result.json()
    sid = post("/api/sessions", {"title": "独立内存采样 " + kind})["session_id"]
    began = time.monotonic(); confirmations = 0
    run = post(f"/api/sessions/{sid}/runs", {"request_id": uuid.uuid4().hex, "task": task, "mode": "taint_policy", "seed": seed,
                                           "document_ids": docs, "recipient_id": recipient, "export_path": export, "private_mode": False})
    rid = run["run_id"]; error = None
    try:
        while run["status"] in ("running", "pending", "stopping"):
            if time.monotonic() - began > 250: raise TimeoutError("Demonstration task deadline exceeded")
            if run["status"] == "pending":
                if confirmations >= 6: raise RuntimeError("Confirmation bound reached")
                # Uniformly approve only the gateway's already-authorized pending action.
                run = post(f"/api/sessions/{sid}/runs/{rid}/confirm", {"request_id": uuid.uuid4().hex, "action_hash": run["pending"]["action_hash"], "approve": True})
                confirmations += 1
            else:
                time.sleep(.1)
                reply = client.get(f"/api/sessions/{sid}/runs/{rid}"); reply.raise_for_status(); run = reply.json()
    except Exception as exc:
        error = type(exc).__name__
        post(f"/api/sessions/{sid}/runs/{rid}/stop", {})
        deadline = time.monotonic() + 30
        while run["status"] in ("running", "pending", "stopping") and time.monotonic() < deadline:
            time.sleep(.2); reply=client.get(f"/api/sessions/{sid}/runs/{rid}"); reply.raise_for_status(); run=reply.json()
    elapsed = time.monotonic() - began
    if run["backend_type"] != "local_llama_cpp": raise RuntimeError("Not a real local model backend")
    state = run["state"]
    return {"kind": kind, "run_id": rid, "seed": seed, "status": run["status"], "backend_type": run["backend_type"],
            "wall_seconds_including_API_polling_and_automatic_confirmation": round(elapsed, 6),
            "confirmation_events": confirmations, "confirmation_actor": "automated measurement client, not human labor", "usage": run["usage"],
            "events": [{k:e.get(k) for k in ("step", "tool", "decision", "reason")} for e in run["events"]], "final_reply": run.get("final", ""),
            "state_evidence": {"reads": state["reads"], "search_queries": state["search_queries"], "inbox": state["inbox"], "files": [{"path":x["path"],"content":x["content"]} for x in state["files"]]},
            "task_verified_by_actual_state_and_content": task_success(kind, run), "error_type": error}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--execute",action="store_true");p.add_argument("--output-dir",type=Path)
    p.add_argument("--interval",type=float,default=.5);p.add_argument("--gpu-interval",type=float,default=1);p.add_argument("--idle-seconds",type=float,default=4);p.add_argument("--seed",type=int,default=11)
    args=p.parse_args(argv)
    if not args.execute:p.error("Pass --execute to sample real processes and submit four local demonstration tasks")
    if os.name!="nt":p.error("This sampler is validated on Windows only")
    if not .1<=args.interval<=5 or not .5<=args.gpu_interval<=10 or not 2<=args.idle_seconds<=30:p.error("Sampling intervals/idle duration are outside bounded ranges")
    dest=args.output_dir or ROOT/"results/core_features/performance"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if dest.exists():raise ValueError("Choose a new output directory to preserve earlier attempts")
    dest.mkdir(parents=True)
    import httpx
    from project_lifecycle import Project, norm
    from verify_launcher_windows import protected_hash, service_ids
    from verify_model_offline_windows import active_runs
    from taintlab.experiments import runtime_fingerprint
    project=Project();initial=project.inspect()
    if not all(x["healthy"] and len(x["owned"])==1 and not x["conflicts"] for x in initial.values()):raise RuntimeError("Own model/UI must already be verified healthy; sampler never starts services")
    if active_runs(ROOT/"results/v2/web_private/sessions.sqlite"):raise RuntimeError("Another task is active; do not overlap controlled measurement")
    report={"started_at_utc":datetime.now(timezone.utc).isoformat(),"kind":"small_real_local_model_memory_measurement","formal_experiment":False,
            "scope":"Warm existing services on one Windows host; four sequential demo tasks, not a benchmark or before/after optimization comparison",
            "process_scope":"Actual listening Python UI process and llama-server only; excludes venv redirector, browser and sampler process",
            "python":sys.version,"platform":platform.platform(),"runtime_sha256":runtime_fingerprint(),"model_lock":json.loads((ROOT/"configs/model.lock.json").read_text("utf-8")),
            "nominal_memory_interval_seconds":args.interval,"nominal_device_gpu_interval_seconds":args.gpu_interval,"idle_seconds_each":args.idle_seconds,
            "metric_definitions":{"working_set_bytes":"PROCESS_MEMORY_COUNTERS_EX.WorkingSetSize: current resident working set, includes potentially shared pages",
                                  "private_commit_bytes":"PROCESS_MEMORY_COUNTERS_EX.PrivateUsage: private committed bytes; not the resident subset",
                                  "observed_peak":"Maximum measured current value in this phase, not process-lifetime peak and not a guarantee of the instantaneous maximum",
                                  "device_memory_used_mib":"nvidia-smi total GPU-device occupancy, may include other applications; NOT model process VRAM"},
            "protected_before":protected_hash(ROOT),"tasks":[],"processes":{},"all_passed":False,"errors":[]}
    stop=threading.Event();phase={"value":"idle_before"};memory=[];gpu=[];readers={};threads=[];start=time.monotonic()
    def save():
        (dest/"measurement.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    try:
        for role in ("model","ui"):
            identity=initial[role]["owned"][0];reader=ProcessMemory(identity["pid"],identity["created"])
            if norm(reader.identity["exe"])!=norm(identity["exe"]):reader.close();raise RuntimeError("Process executable identity changed")
            readers[role]=reader;report["processes"][role]={"pid":identity["pid"],"creation_time":identity["created"],"executable_name":Path(identity["exe"]).name,"project_identity_verified":True}
        def memory_loop():
            while not stop.is_set():
                stamp=time.monotonic()-start;label=phase["value"]
                for role,reader in readers.items():
                    item={"seconds_from_start":round(stamp,6),"phase":label,"role":role,"pid":report["processes"][role]["pid"]}
                    try:item.update(reader.read())
                    except Exception as exc:item["error"]=type(exc).__name__
                    memory.append(item)
                stop.wait(args.interval)
        nvidia=shutil.which("nvidia-smi")
        def gpu_loop():
            if not nvidia:return
            while not stop.is_set():
                label=phase["value"];stamp=time.monotonic()-start
                try:
                    result=subprocess.run([nvidia,"--query-gpu=index,name,driver_version,memory.used,memory.total,utilization.gpu","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=3,creationflags=subprocess.CREATE_NO_WINDOW)
                    if result.returncode:raise RuntimeError("nvidia-smi query failed")
                    gpu.append({"seconds_from_start":round(stamp,6),"phase":label,"devices":parse_gpu_csv(result.stdout)})
                except Exception as exc:gpu.append({"seconds_from_start":round(stamp,6),"phase":label,"error":type(exc).__name__})
                stop.wait(args.gpu_interval)
        threads=[threading.Thread(target=memory_loop,daemon=True),threading.Thread(target=gpu_loop,daemon=True)]
        for thread in threads:thread.start()
        time.sleep(args.idle_seconds)
        phase["value"]="bootstrap"
        base=f"http://127.0.0.1:{project.ports['ui']}"
        with httpx.Client(base_url=base,trust_env=False,timeout=30) as client:
            boot=client.get("/api/bootstrap");boot.raise_for_status();payload=boot.json()
            if not payload["model"]["available"]:raise RuntimeError("Local model unavailable")
            client.headers.update({"Origin":base,"X-TaintLab-CSRF":payload["csrf_token"]})
            for spec in TASKS:
                phase["value"]="task_"+spec[0]
                result=run_task(client,spec,args.seed);report["tasks"].append(result);save()
                print(f"{spec[0]} run_id={result['run_id']} status={result['status']} tools={result['usage'].get('tool_calls')} wall={result['wall_seconds_including_API_polling_and_automatic_confirmation']:.3f}s",flush=True)
                if result["status"] in ("running","pending","stopping"):raise RuntimeError("Task did not stop; do not begin other concurrent measurements")
        phase["value"]="idle_after";time.sleep(args.idle_seconds)
    except Exception as exc:
        report["errors"].append({"type":type(exc).__name__});raise
    finally:
        stop.set()
        for thread in threads:thread.join(timeout=5)
        for reader in readers.values():reader.close()
        for name,rows in (("process_memory.jsonl",memory),("gpu_device.jsonl",gpu)):
            (dest/name).write_text("".join(json.dumps(row,ensure_ascii=False)+"\n" for row in rows),encoding="utf-8")
        report["memory_summary"]=summary(memory);report["sample_errors"]=[x for x in memory if "error" in x]
        stamps=sorted({x["seconds_from_start"] for x in memory});gaps=[b-a for a,b in zip(stamps,stamps[1:])]
        report["actual_memory_interval_seconds"]={"min":min(gaps),"median":statistics.median(gaps),"max":max(gaps)} if gaps else None
        report["gpu_available"]=bool(nvidia) if "nvidia" in locals() else False
        report["gpu_process_memory_measured"]=False
        report["gpu_device_observed_peak_used_mib"]=max((d["device_memory_used_mib"] for x in gpu for d in x.get("devices",[]) if d["device_memory_used_mib"] is not None),default=None)
        report["protected_after"]=protected_hash(ROOT);final=project.inspect()
        report["original_services_healthy_and_same_identity"]=all(x["healthy"] for x in final.values()) and service_ids(initial)==service_ids(final)
        report["runtime_unchanged"]=report["runtime_sha256"]==runtime_fingerprint()
        report["formal_evidence_unchanged"]=report["protected_before"]==report["protected_after"]
        report["all_passed"]=not report["errors"] and not report["sample_errors"] and len(report["tasks"])==4 and all(x["task_verified_by_actual_state_and_content"] for x in report["tasks"]) and report["formal_evidence_unchanged"] and report["runtime_unchanged"] and report["original_services_healthy_and_same_identity"]
        report["finished_at_utc"]=datetime.now(timezone.utc).isoformat();save()
    print(json.dumps({"output":str(dest),"all_passed":report["all_passed"],"memory_samples":len(memory),"gpu_samples":len(gpu),"formal_experiment":False},ensure_ascii=False),flush=True)
    return 0 if report["all_passed"] else 1


if __name__=="__main__":raise SystemExit(main())
