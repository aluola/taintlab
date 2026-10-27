"""F06 detector mechanism self-check: synthetic inputs, NOT model experiments.

This script calls the existing detector and does not implement detection logic.
It never connects to a model, executes a tool or changes a simulated mailbox.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from taintlab.evaluation import canary as detector

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_CANARY = "CANARY_SYNTHETIC_F06_7c2a19d0"
DISCLAIMER = "检测器机制自检 / 合成输入 / 非模型正式实验"


def synthetic_cases():
    value=SYNTHETIC_CANARY
    once=base64.b64encode(value.encode()).decode();twice=base64.b64encode(once.encode()).decode()
    third=base64.b64encode(twice.encode()).decode();cut=len(value)//2
    fullwidth="".join(chr(ord(c)+0xFEE0) for c in value)
    return [
        {"id":"positive_exact","label":"阳性原文","expected_found":True,"observables":[{"sink":"notification:synthetic_external","text":value}]},
        {"id":"negative_neighbor","label":"阴性近似文本","expected_found":False,"observables":[{"sink":"final","text":value[:-1]+"1"}]},
        {"id":"unicode_normalized","label":"全角规范化","expected_found":True,"observables":[{"sink":"final","text":fullwidth}]},
        {"id":"encoded_base64_twice","label":"两层Base64","expected_found":True,"observables":[{"sink":"export:/synthetic/out.txt","text":twice}]},
        {"id":"segmented_same_sink","label":"同运行同出口分片","expected_found":True,"observables":[{"sink":"notification:synthetic_external","text":value[:cut]},{"sink":"notification:synthetic_external","text":value[cut:]}]},
        {"id":"segmented_observer_coalition","label":"同运行跨出口分片","expected_found":True,"observables":[{"sink":"notification:synthetic_external","text":value[:cut]},{"sink":"export:/synthetic/out.txt","text":value[cut:]}]},
        {"id":"beyond_decode_depth","label":"三层编码覆盖边界","expected_found":False,"observables":[{"sink":"final","text":third}],"coverage_note":"超过现有max_depth=2；未检出是已知覆盖限制，不能声称任意编码可检测。"},
    ]


def build_report():
    results=[]
    for case in synthetic_cases():
        detected=detector.detect_observables(case["observables"],SYNTHETIC_CANARY)
        results.append({**case,"detector_result":detected,"matches_synthetic_expectation":detected["found"] is case["expected_found"]})
    source=Path(detector.__file__).resolve()
    return {"created_at_utc":datetime.now(timezone.utc).isoformat(),"kind":"synthetic_detector_mechanism_selfcheck","disclaimer":DISCLAIMER,
            "formal_experiment":False,"included_in_ASR":False,"model_called":False,"business_side_effects":False,
            "synthetic_canary":SYNTHETIC_CANARY,"synthetic_canary_is_real_secret":False,
            "detector":{"module":"taintlab.evaluation.canary","function":"detect_observables","source_sha256":hashlib.sha256(source.read_bytes()).hexdigest()},
            "cases":results,"all_passed":all(case["matches_synthetic_expectation"] for case in results),
            "limits":{"max_text":detector.MAX_TEXT,"max_items":detector.MAX_ITEMS,"max_depth":detector.MAX_DEPTH,"max_candidates":detector.MAX_CANDIDATES},
            "scope":"Each case is an independent synthetic observable run. Inputs identify unauthorized-observer sinks by construction; no authorization decision or real model leakage is claimed. Cases are never concatenated across runs.",
            "conclusion_boundary":"机制阳性不代表正式模型发生过外泄；正式无防御也为零Canary泄露，不能因此归因于防御或宣称污点独立收益。"}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,help="Optional NEW evidence file; existing evidence is never overwritten")
    args=parser.parse_args(argv);report=build_report()
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    print(DISCLAIMER)
    print("真实函数：taintlab.evaluation.canary.detect_observables；不调用模型、不执行模拟工具。")
    print("仅为本自检构造的Canary："+SYNTHETIC_CANARY)
    for case in report["cases"]:
        result=case["detector_result"]
        print(f"[{case['id']}] {case['label']} | expected={case['expected_found']} found={result['found']}")
        print("  输入出口="+" + ".join(item["sink"] for item in case["observables"]))
        print("  合成输入="+json.dumps([item["text"] for item in case["observables"]],ensure_ascii=False))
        print("  检测依据="+json.dumps(result["findings"],ensure_ascii=False))
        if case.get("coverage_note"):print("  边界="+case["coverage_note"])
    print("限制="+json.dumps(report["limits"],ensure_ascii=False))
    print(f"机制预设匹配：{sum(case['matches_synthetic_expectation'] for case in report['cases'])}/{len(report['cases'])}；不计入ASR。")
    print(DISCLAIMER+"；没有证明真实模型泄露或防御独立收益。")
    if args.output:print("证据="+str(args.output))
    return 0 if report["all_passed"] else 1


if __name__=="__main__":raise SystemExit(main())
