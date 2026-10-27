"""Pure helpers for rendering persisted evidence, never for security decisions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MODES = {
    "none": "A · 无防御",
    "input_filter": "B · 仅输入过滤",
    "taint_policy": "C · 污点追踪加权限策略",
    "policy_only": "补充 · 仅权限策略",
}
STATUS = {
    "completed": "已结束",
    "pending": "等待真实人工确认",
    "exhausted": "预算耗尽",
    "timeout": "超时",
    "model_error": "模型服务错误",
    "parse_error": "动作解析失败",
}
DECISIONS = {"allow": "允许", "block": "阻断", "pending": "待确认", "error": "错误"}


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def read_cases(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    cases = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            row = json.loads(line)
            if isinstance(row.get("runtime"), dict):
                cases.append(row)
    return cases


def source_nodes(record: dict) -> list[dict]:
    nodes = record.get("nodes", [])
    return list(nodes.values()) if isinstance(nodes, dict) else nodes


def action_hash(action: dict) -> str:
    """A display-only digest. The execution gateway owns the real credential."""
    text = json.dumps(action, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def event_rows(record: dict) -> list[dict]:
    rows = []
    for index, event in enumerate(record.get("events", [])):
        action = event.get("action") or {}
        if not isinstance(action, dict):
            action = {}
        rows.append({
            "步骤": event.get("step", index + 1),
            "动作": action.get("tool", action.get("type", "系统事件")),
            "决策": DECISIONS.get(event.get("decision"), event.get("decision", "—")),
            "原因": str(event.get("reason", "")),
            "节点": event.get("node_id", ""),
        })
    return rows


def provenance_dot(record: dict, limit: int = 70) -> str:
    """Escaped labels; styles distinguish potential from deterministic edges."""
    nodes = source_nodes(record)[-limit:]
    ids = {str(node.get("node_id")) for node in nodes}
    dot = [
        "digraph provenance {",
        'graph [rankdir=LR, bgcolor="transparent", pad="0.25", nodesep="0.25", ranksep="0.65"];',
        'node [shape=box, style="rounded,filled", fontname="Microsoft YaHei", fontsize=11, color="#CBD5E1", margin="0.15,0.12"];',
        'edge [fontname="Microsoft YaHei", fontsize=9, color="#94A3B8"];',
    ]
    for node in nodes:
        ident = str(node.get("node_id"))
        sensitivity = str(node.get("sensitivity", "unknown"))
        integrity = str(node.get("integrity", "unknown"))
        fill = {"secret": "#FEE2E2", "internal": "#FEF3C7", "public": "#E0F2FE"}.get(sensitivity, "#F1F5F9")
        label = "\n".join([
            ident[:24], str(node.get("source_type", "")) + " / " + str(node.get("source_id", ""))[:24],
            integrity + " · " + sensitivity,
        ])
        dot.append(f"{json.dumps(ident)} [label={json.dumps(label, ensure_ascii=False)}, fillcolor={json.dumps(fill)}];")
        transform = str(node.get("transformation", ""))
        potential = node.get('dependency_kind')=='potential_context' or any(word in transform.lower() for word in ("model", "generation", "context", "potential"))
        edge_label = "潜在上下文依赖" if potential else "确定性派生"
        style = "dashed" if potential else "solid"
        for parent in node.get("parent_ids", []):
            if str(parent) in ids:
                dot.append(f'{json.dumps(str(parent))} -> {json.dumps(ident)} [style="{style}", label="{edge_label}"];')
    dot.append("}")
    return "\n".join(dot)


def metric_rows(summary: Any) -> list[dict]:
    if not isinstance(summary, dict):
        return summary if isinstance(summary, list) else []
    for name in ("modes", "by_mode", "configurations", "groups", "results"):
        obj = summary.get(name)
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            return [{"mode": key, **value} for key, value in obj.items() if isinstance(value, dict)]
    if any(mode in summary for mode in MODES):
        return [{"mode": key, **value} for key, value in summary.items() if key in MODES and isinstance(value, dict)]
    return []


def save_record(root: Path, record: dict) -> Path:
    """Persist to a trusted directory using an opaque filename, never model paths."""
    destination = root / "results" / "demo" / "records"
    destination.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha256(str(record["run_id"]).encode()).hexdigest()[:24] + ".json"
    path = destination / name
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path


def history_files(root: Path) -> list[Path]:
    paths = []
    for group in ("demo", "main", "smoke", "ablation"):
        folder = root / "results" / group / "records"
        if folder.is_dir():
            paths.extend(folder.glob("*.json"))
    return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)
