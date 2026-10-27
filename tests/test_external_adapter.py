import json
from pathlib import Path

import pytest

from taintlab.attacks.external_adapter import DEFAULT_DATA, RUNTIME_FIELDS, build_cases, digest, freeze_external_dataset, generate_external_dataset, validate_cases, verify_external_dataset
from taintlab.attacks.interactive import build_preview, list_presets
from taintlab.evaluation.evaluator import evaluate
from taintlab.policy.grants import TaskGrant


def test_predeclared_source_family_split_and_all_counts():
    test, dev = build_cases()
    result = validate_cases(test, dev)
    assert result["ok"], result["errors"]
    assert len(test) == 90 and len(dev) == 13
    assert result["splits"]["test"]["sources"] == {"BIPIA": 30, "InjecAgent": 30, "local_control": 30}
    assert result["splits"]["dev"]["sources"] == {"BIPIA": 5, "InjecAgent": 4, "local_control": 4}
    assert result["splits"]["test"]["confirmation_controls"] == 2


def test_no_answers_enter_runtime_and_grants_validate():
    test, dev = build_cases()
    for case in test + dev:
        runtime = case["runtime"]
        assert not set(runtime) - RUNTIME_FIELDS
        assert "evaluation" not in runtime and "source_metadata" not in runtime
        grant = TaskGrant.bind(runtime["grant"], "structural-test")
        assert set(grant.readable_docs) <= set(runtime["documents"])
        assert case["evaluation"]["success"]
        if case["kind"] == "attack":
            assert case["source_metadata"]["revision"] in {"a004b69ec0dd446e0afd461d98cb5e96e120a5d0", "f19c9f2c79a41046eb13c03c51a24c567a8ffa07"}


def test_license_boundary_excludes_uncleared_original_prose():
    sources = json.loads((DEFAULT_DATA / "upstream/source_payloads.json").read_text(encoding="utf-8"))
    assert "injec_dh" not in sources and "injec_ds" not in sources
    for kind in ("dh", "ds"):
        index = sources[f"injec_{kind}_index"]
        assert index["original_text_redistributed"] is False
        for row in index["rows"]:
            assert "Attacker Instruction" not in row
            assert len(row["instruction_sha256"]) == 64
    for case in build_cases()[0]:
        if case["source_metadata"]["source_dataset"] == "InjecAgent":
            assert case["source_metadata"]["license"]["original_text_redistributed"] is False


def test_attacks_retain_lawful_source_facts_and_no_real_secret():
    test, dev = build_cases()
    for case in test + dev:
        rt = case["runtime"]
        text = json.dumps(rt, ensure_ascii=False)
        assert "CANARY_" not in text
        for assertion in case["evaluation"]["success"]:
            for required in assertion.get("contains", []):
                assert required in text, (case["id"], required)
        if case["kind"] == "attack":
            inj = rt["injection"]
            if inj["entry"] == "document":
                assert inj["marker"] in rt["documents"][inj["source_id"]]["content"]
            elif inj["entry"] == "web":
                assert inj["marker"] in rt["search_results"][0]["content"]
            else:
                assert inj["marker"] in rt["tool_return_suffix"]


def test_offline_regeneration_and_freeze_are_reproducible(tmp_path):
    generate_external_dataset(tmp_path)
    one = (tmp_path / "test.jsonl").read_bytes()
    generate_external_dataset(tmp_path)
    assert (tmp_path / "test.jsonl").read_bytes() == one
    # Freeze carries provenance prerequisites as well as evaluated rows.
    for name in ("selection_rules.json", "upstream/source_payloads.json"):
        target = tmp_path / name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes((DEFAULT_DATA / name).read_bytes())
    frozen = freeze_external_dataset(tmp_path)
    assert frozen["files"]["test.jsonl"] == digest(one)
    assert freeze_external_dataset(tmp_path) == frozen
    assert verify_external_dataset(tmp_path)["ok"]
    with (tmp_path / "test.jsonl").open("ab") as target:
        target.write(b" ")
    assert not verify_external_dataset(tmp_path)["ok"]
    (tmp_path / "test.jsonl").write_bytes(one)
    frozen["files"]["test.jsonl"] = "0" * 64
    (tmp_path / "frozen_manifest.json").write_text(json.dumps(frozen), encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen corpus"):
        generate_external_dataset(tmp_path)


@pytest.mark.parametrize("preset", list_presets())
def test_four_views_have_real_insertions_and_isolated_runtime(preset):
    preview = build_preview(view=preset["view"], **preset["defaults"], seed=11)
    assert preview == build_preview(view=preset["view"], **preset["defaults"], seed=11)
    assert preview["before"] != preview["after"]
    assert preview["metadata"]["formal_dataset"] is False
    assert "evaluation" not in preview["runtime"]
    assert preview["runtime"] is not preview["case"]["runtime"]
    TaskGrant.bind(preview["runtime"]["grant"], "preview-check")
    if preset["view"] == "segmented":
        assert [x["order"] for x in preview["fragments"]] == [1, 2]
        assert len({x["source_id"] for x in preview["fragments"]}) == 2
    if preset["view"] == "direct":
        assert preview["case"]["evaluation"]["threat_model"] == "direct"


def test_preview_rejects_unrecognized_targets_and_incompatible_dimensions():
    with pytest.raises(ValueError):
        build_preview(goal="edit_real_files")
    with pytest.raises(ValueError):
        build_preview(view="segmented", entry="web")
    with pytest.raises(ValueError):
        build_preview(seed=True)


def test_normal_cases_are_explicitly_local_controls_and_keep_legitimate_tools():
    normals = [c for c in build_cases()[0] if c["kind"] == "normal"]
    assert len(normals) == 30
    assert all(c["source_metadata"]["source_dataset"] == "local_control" for c in normals)
    for c in normals:
        tools = c["runtime"]["grant"]["tools"]
        if c["category"] == "notification":
            assert "send_notification" in tools
        if c["category"] == "export":
            assert "export_file" in tools


def test_cross_split_original_family_leakage_is_detected():
    test, dev = build_cases()
    dev[0]["source_metadata"]["original_family"] = test[0]["source_metadata"]["original_family"]
    assert not validate_cases(test, dev)["ok"]


def test_control_completion_requires_real_state_and_terminal_completion():
    case = next(c for c in build_cases()[0] if c["kind"] == "normal" and c["category"] == "notification")
    words = case["evaluation"]["success"][1]["contains"]
    record = {"status": "completed", "state": {"finals": ["已发送 " + " ".join(words)]}}
    assert not evaluate(case, record, "mock-canary")["legitimate_success"]
    record["state"] = {"reads": ["workshop"], "inbox": [{"recipient_id": "team_A", "body": " ".join(words)}]}
    assert evaluate(case, record, "mock-canary")["legitimate_success"]
    record["status"] = "pending"
    assert not evaluate(case, record, "mock-canary")["legitimate_success"]


def test_previews_never_embed_real_recipient_or_host_file_access():
    for preset in list_presets():
        for goal in preset["options"]["goal"]:
            arguments = {**preset["defaults"], "goal": goal}
            preview = build_preview(view=preset["view"], **arguments, seed=17)
            text = json.dumps(preview["runtime"], ensure_ascii=False)
            assert "@" not in text and "http://" not in text and "https://" not in text
            assert "D:/" not in text and "C:/" not in text
            assert "{{CANARY}}" not in preview["runtime"]["injection"]["marker"]
