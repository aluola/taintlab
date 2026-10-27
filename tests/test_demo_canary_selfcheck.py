"""Synthetic detector demonstration tests; never formal/model experiments."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import demo_canary_selfcheck as demo


def test_delegates_every_case_to_existing_detector(monkeypatch):
    original=demo.detector.detect_observables;calls=[]
    def observed(items,canary):
        calls.append((items,canary));return original(items,canary)
    monkeypatch.setattr(demo.detector,"detect_observables",observed)
    report=demo.build_report()
    assert len(calls)==len(report["cases"])==7
    assert all(canary==demo.SYNTHETIC_CANARY for _,canary in calls)
    assert report["all_passed"]


def test_results_include_positive_negative_methods_and_segmented_sinks():
    report=demo.build_report();cases={case["id"]:case for case in report["cases"]}
    assert cases["positive_exact"]["detector_result"]["findings"]==[{"sink":"notification:synthetic_external","method":"exact","segmented":False}]
    assert not cases["negative_neighbor"]["detector_result"]["found"]
    assert any(item["method"]=="exact+base64+base64" for item in cases["encoded_base64_twice"]["detector_result"]["findings"])
    assert any(item["segmented"] for item in cases["segmented_same_sink"]["detector_result"]["findings"])
    assert any(item["sink"]=="unauthorized_observer_coalition" for item in cases["segmented_observer_coalition"]["detector_result"]["findings"])


def test_known_depth_limit_is_explained_not_claimed_unlimited():
    report=demo.build_report();case=next(c for c in report["cases"] if c["id"]=="beyond_decode_depth")
    assert not case["detector_result"]["found"] and case["matches_synthetic_expectation"]
    assert "max_depth=2" in case["coverage_note"] and report["limits"]["max_depth"]==2
    assert report["formal_experiment"] is False and report["included_in_ASR"] is False and report["model_called"] is False


def test_cli_evidence_labels_and_no_existing_output_overwrite(tmp_path,capsys):
    output=tmp_path/"selfcheck.json"
    assert demo.main(["--output",str(output)])==0
    text=capsys.readouterr().out
    assert text.count(demo.DISCLAIMER)>=2 and "expected=False found=False" in text
    content=output.read_bytes()
    assert json.loads(content)["all_passed"]
    with pytest.raises(FileExistsError):demo.main(["--output",str(output)])
    assert output.read_bytes()==content
