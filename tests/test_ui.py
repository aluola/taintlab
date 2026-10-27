"""Evidence presentation must not make simulation paths host-write targets."""
import json
from pathlib import Path

from taintlab.ui.viewmodel import action_hash, event_rows, metric_rows, provenance_dot, read_cases, save_record


def test_audit_graph_keeps_dependency_kind_and_escapes_labels():
    record = {"nodes": [
        {"node_id": "a", "source_id": 'evil\" ]; x -> y', "sensitivity": "secret", "integrity": "untrusted_content", "parent_ids": []},
        {"node_id": "b", "source_id": "action", "transformation": "model_generation", "parent_ids": ["a"]},
        {"node_id": "c", "transformation": "slice", "parent_ids": ["b"]},
    ]}
    dot = provenance_dot(record)
    assert 'style="dashed"' in dot and "潜在上下文依赖" in dot
    assert 'style="solid"' in dot and "确定性派生" in dot
    assert 'evil\\\"' in dot


def test_ui_save_does_not_follow_run_id_path(tmp_path):
    record = {"run_id": "../../outside", "state": {"files": {"C:/escape": "simulated"}}}
    path = save_record(tmp_path, record)
    assert path.parent == tmp_path / "results" / "demo" / "records"
    assert json.loads(path.read_text(encoding="utf-8")) == record
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_pending_event_is_not_displayed_as_execution():
    rows = event_rows({"events": [{"step": 1, "action": {"tool": "send_notification"}, "decision": "pending", "reason": "confirmation_required"}]})
    assert rows[0]["决策"] == "待确认"


def test_display_hash_binds_changed_arguments():
    first = {"tool": "export_file", "arguments": {"path": "/exports/a", "content": "one"}}
    second = {"arguments": {"content": "one", "path": "/exports/a"}, "tool": "export_file"}
    assert action_hash(first) == action_hash(second)
    second["arguments"]["content"] = "two"
    assert action_hash(first) != action_hash(second)


def test_summary_modes_are_read_without_invented_values():
    assert metric_rows({"modes": {"none": {"asr": 0.25}}}) == [{"mode": "none", "asr": 0.25}]
    assert metric_rows({}) == []


def test_case_reader_only_accepts_runtime_records(tmp_path):
    path = tmp_path / "data.jsonl"
    path.write_text('{"id":"n1","runtime":{"task":"hello"},"evaluation":{"hidden":true}}\n', encoding="utf-8")
    cases = read_cases(path)
    assert cases[0]["runtime"] == {"task": "hello"}


def test_streamlit_renders_empty_and_completed_evidence(monkeypatch, tmp_path):
    """Run the actual app, with an explicitly synthetic backend only in this test."""
    from streamlit.testing.v1 import AppTest
    from taintlab.ui import viewmodel
    from taintlab.agent import runtime

    case = {"id": "ui_test", "kind": "normal", "split": "test", "category": "query", "runtime": {
        "task": "查询测试会议", "documents": {}, "grant": {},
    }}
    record = {"run_id": "ui-test-only", "backend_type": "scripted_test", "mode": "taint_policy", "seed": 11,
              "status": "completed", "final": "测试已交付答复", "events": [], "nodes": [], "state": {},
              "usage": {}, "elapsed_seconds": 0.01}
    monkeypatch.setattr(viewmodel, "read_cases", lambda _: [case])
    monkeypatch.setattr(viewmodel, "save_record", lambda _, obj: tmp_path / "test.json")
    monkeypatch.setattr(runtime, "run_case", lambda *args, **kwargs: dict(record))
    app_path = Path(__file__).parents[1] / "src" / "taintlab" / "ui" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=30)
    assert not app.exception
    assert app.button[0].label == "运行本地模型案例"
    app.button[0].click().run(timeout=30)
    assert not app.exception
    assert any("测试后端" in element.value for element in app.error)
    assert any(element.value == "测试已交付答复" for element in app.text)
