"""Read-only v2 campaign re-evaluation; never calls a model or edits raw runs.

Use --campaign baseline while only that batch is complete. The default signs
off both campaigns only after every prespecified record and index is present.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import re

from taintlab.evaluation.evaluator import evaluate, summarize

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGNS = {"baseline": ("data/test.jsonl", 108, 1296), "external": ("data/v2/test.jsonl", 90, 1080)}
MODES = ["none", "input_filter", "taint_policy", "policy_only"]
SEEDS = [11, 23, 47]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def jsonl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8-sig").splitlines() if x.strip()]


def current_runtime_hash(root):
    files = []
    for folder in ("agent", "model", "policy", "provenance", "tools", "evaluation"):
        files.extend(p.relative_to(root) for p in (root / "src/taintlab" / folder).glob("*.py"))
    # Match the frozen runner's mixed path representation: the absolute
    # experiments.py key precedes its relative module paths on this platform.
    files.append(root / "src/taintlab/experiments.py")
    return hashlib.sha256(b"".join((root / p).read_bytes() for p in sorted(files))).hexdigest()


def inspect_campaign(root, campaign):
    dataset, case_count, run_count = CAMPAIGNS[campaign]
    folder = root / "results/v2" / campaign
    manifest = read(folder / "experiment_manifest.json")
    lock = read(root / "configs/experiment_v2.lock.json")["signature"]
    cases = {c["id"]: c for c in jsonl(root / dataset)}
    pairs = read(folder / "paired_scenarios.json")
    files = sorted((folder / "records").glob("*.json"))
    records = [read(p) for p in files]
    checks = {
        "expected_case_count": len(cases) == case_count,
        "planned_run_count": manifest["planned_runs"] == run_count,
        "raw_record_count": len(records) == run_count,
        "modes_and_seeds_frozen": manifest["modes"] == MODES and manifest["seeds"] == SEEDS,
        "dataset_hash": manifest["dataset_sha256"] == sha(root / dataset),
        "runtime_frozen_and_current": manifest["runtime_sha256"] == lock["runtime_sha256"] == current_runtime_hash(root),
        "model_lock_hash": manifest["model_lock_sha256"] == sha(root / "configs/model.lock.json"),
        "shared_model_config": manifest["model_config"] == read(root / "configs/model.json"),
        "manifest_backend_local": manifest["backend_type"] == "local_llama_cpp",
        "confirmation_mode": manifest["confirmation_mode"] == "simulate_authorized",
    }
    identifiers = [r["run_id"] for r in records]
    keys = [(r["case_id"], r["seed"], r["mode"]) for r in records]
    checks["unique_identity_and_grid"] = len(set(identifiers)) == run_count and len(set(keys)) == run_count and set(keys) == set(itertools.product(cases, SEEDS, MODES))
    checks["filename_identity"] = all(p.stem == r["run_id"] for p, r in zip(files, records))
    checks["all_backend_local"] = all(r["backend_type"] == "local_llama_cpp" for r in records)
    checks["stable_run_ids"] = all(r["run_id"] == hashlib.sha256((manifest["dataset_sha256"] + manifest["runtime_sha256"] + r["case_id"] + str(r["seed"]) + r["mode"]).encode()).hexdigest()[:24] for r in records)
    checks["paired_scenarios_complete"] = set(pairs) == {f"{case}:{seed}" for case in cases for seed in SEEDS}
    checks["canary_shape_and_unique_scenarios"] = len(set(pairs.values())) == case_count * len(SEEDS) and all(re.fullmatch(r"CANARY_[0-9a-f]{32}", value) for value in pairs.values())
    materialization_matches = []
    grant_matches = []
    for record in records:
        case = cases[record["case_id"]]
        expected_runtime = json.loads(json.dumps(case["runtime"]))
        canary = pairs[f"{case['id']}:{record['seed']}"]
        # Canary materialization is confined to the declared documents. Local
        # search snapshots may retain a literal placeholder; they are not keys.
        for document in expected_runtime.get("documents", {}).values():
            document["content"] = document["content"].replace("{{CANARY}}", canary)
        materialization_matches.append(record.get("_checkpoint", {}).get("runtime") == expected_runtime)
        grant_matches.append(all(record["grant"].get(k) == v for k, v in case["runtime"]["grant"].items()) and record["grant"].get("run_id") == record["run_id"])
    checks["actual_paired_initial_runtime"] = all(materialization_matches)
    checks["actual_grants_match_frozen_cases"] = all(grant_matches)
    checks["record_model_config_identical"] = all(r.get("model_config") == manifest["model_config"] for r in records)
    checks["record_confirmation_mode_identical"] = all(r.get("confirmation_mode") == manifest["confirmation_mode"] for r in records)
    recomputed = []
    assessment_mismatches = []
    for record in records:
        case = cases[record["case_id"]]
        row = evaluate(case, record, pairs[f"{case['id']}:{record['seed']}"])
        if row != record.get("assessment"):
            assessment_mismatches.append(record["run_id"])
        recomputed.append(row)
    recomputed.sort(key=lambda row: (row["case_id"], row["seed"], row["mode"]))
    indexed = jsonl(folder / "metrics.jsonl")
    summary = summarize(recomputed)
    saved_summary = read(folder / "summary.json")
    checks["raw_assessments_exact"] = not assessment_mismatches
    checks["metrics_jsonl_exact"] = recomputed == indexed
    checks["summary_exact"] = summary == {k: v for k, v in saved_summary.items() if k != "manifest"} and saved_summary.get("manifest") == manifest
    with (folder / "metrics.csv").open(encoding="utf-8-sig", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    fields = sorted(set().union(*(r.keys() for r in recomputed)))
    expected_csv = [{k: json.dumps(row.get(k), ensure_ascii=False) if isinstance(row.get(k), (list, dict)) else "" if row.get(k) is None else str(row.get(k)) for k in fields} for row in recomputed]
    checks["metrics_csv_exact"] = csv_rows == expected_csv
    per_mode_seed = {f"{mode}:{seed}": sum(r["mode"] == mode and r["seed"] == seed for r in recomputed) for mode in MODES for seed in SEEDS}
    checks["each_mode_seed_denominator"] = all(count == case_count for count in per_mode_seed.values())
    index = {p.name: sha(p) for p in files}
    source_files = {str((folder / name).relative_to(root)).replace("\\", "/"): sha(folder / name) for name in ("experiment_manifest.json", "paired_scenarios.json", "metrics.jsonl", "metrics.csv", "summary.json")}
    rows = {(r["case_id"], r["seed"], r["mode"]): r for r in recomputed}
    differences = []
    for row in recomputed:
        if row["kind"] != "attack" or row["mode"] != "taint_policy":
            continue
        policy = rows[(row["case_id"], row["seed"], "policy_only")]
        if row["attack_success"] != policy["attack_success"]:
            differences.append({"case_id": row["case_id"], "seed": row["seed"], "attack_goal": cases[row["case_id"]]["evaluation"]["attack_goal"], "taint_run_id": row["run_id"], "policy_run_id": policy["run_id"], "taint_success": row["attack_success"], "policy_success": policy["attack_success"], "taint_blocks": row["block_reasons"], "policy_blocks": policy["block_reasons"]})
    result = {"campaign": campaign, "all_passed": all(checks.values()), "checks": checks, "checked_runs": len(records), "backend_counts": {"local_llama_cpp": sum(r["backend_type"] == "local_llama_cpp" for r in records)}, "runtime_sha256": manifest["runtime_sha256"], "dataset_sha256": manifest["dataset_sha256"], "per_mode_seed": per_mode_seed, "raw_records_fingerprint": hashlib.sha256(json.dumps(index, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "source_files_sha256": source_files, "assessment_mismatches": assessment_mismatches, "modes": summary["modes"], "policy_taint_attack_outcome_differences": differences}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", choices=("baseline", "external", "both"), default="both")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    names = list(CAMPAIGNS) if args.campaign == "both" else [args.campaign]
    output = args.output or ROOT / "results/v2/validation" / ("experiment_integrity.json" if args.campaign == "both" else args.campaign + "_integrity.json")
    results = [inspect_campaign(ROOT, name) for name in names]
    report = {"schema_version": "2.0", "created_at_utc": datetime.now(timezone.utc).isoformat(), "scope": "Both frozen v2 campaigns" if args.campaign == "both" else args.campaign + " only; not a full v2 acceptance", "all_passed": all(r["all_passed"] for r in results), "checked_runs": sum(r["checked_runs"] for r in results), "planned_runs": sum(CAMPAIGNS[name][2] for name in names), "model_calls_made_by_validator": 0, "formal_records_modified": False, "campaigns": {r["campaign"]: r for r in results}, "interpretation": "Paired ASR differences alone are not causal evidence of taint benefit. Inspect actual flow blocks and executed violations. Zero Canary leakage in none cannot be attributed to defense."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_passed": report["all_passed"], "checked_runs": report["checked_runs"], "output": str(output), "failed_checks": {name: [k for k, ok in r["checks"].items() if not ok] for name, r in report["campaigns"].items()}}, ensure_ascii=False, indent=2))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
