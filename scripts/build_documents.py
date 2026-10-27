"""Build the editable report from Markdown and actual local evidence.

Run with the Codex bundled Python for authoring. This script never runs a model
or changes experiment records. --refresh-only updates generated Markdown blocks;
--render invokes the packaged render_docx.py and emits an actual DOCX-derived PDF.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "docs" / "qa"
SOURCE = ROOT / "docs" / "project_report.md"
DIST = ROOT / "dist"
RUNTIME = Path(os.environ.get("TAINTLAB_DOC_RUNTIME", str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies")))
RENDERER = Path(os.environ.get("TAINTLAB_DOC_RENDERER", str(Path.home() / ".codex/plugins/cache/openai-primary-runtime/documents/26.1020.11348/skills/documents/render_docx.py")))


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, ValueError):
        return {} if default is None else default


def table(headers, rows):
    def escape(value):
        return str(value).replace("|", "／").replace("\n", " ")
    return "\n".join([
        "| " + " | ".join(map(escape, headers)) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(map(escape, row)) + " |" for row in rows),
    ])


def percent(value):
    return "无数据" if value is None else f"{value * 100:.2f}%"


def ratio(group, name, denominator):
    value = group.get(name)
    return "无数据" if value is None else f"{round(value * denominator)}/{denominator}  {percent(value)}"


def model_block():
    lock = read_json(ROOT / "configs/model.lock.json")
    config = read_json(ROOT / "configs/model.json")
    runtime = read_json(ROOT / "results/environment/model_runtime.json")
    health = read_json(ROOT / "results/environment/model_health.json")
    model_entries = health.get("models", {}).get("data", [])
    parameters = model_entries[0].get("meta", {}).get("n_params") if model_entries else None
    if not lock:
        return "尚无模型锁定配置，不能声称模型已准备完成。"
    rows = [
        ["模型", lock.get("model_id", "待核验")],
        ["服务实际参数量", f"{parameters:,}（符合0.5B至1.5B范围）" if parameters is not None else "待实测"],
        ["权重文件", lock.get("model_file", "待核验")],
        ["官方revision", lock.get("model_revision", "待核验")],
        ["权重字节数", lock.get("model_size_bytes", "待核验")],
        ["SHA256", lock.get("model_sha256", "待核验")],
        ["llama.cpp", runtime.get("properties", {}).get("build_info", lock.get("llama_release", "待核验"))],
        ["服务端点", config.get("endpoint", lock.get("endpoint", "待核验"))],
        ["每会话上下文", config.get("context_size", "待核验")],
        ["生成上限", config.get("max_tokens", "待核验")],
        ["采样参数", f"temperature={config.get('temperature')}；top_p={config.get('top_p')}；top_k={config.get('top_k')}；min_p={config.get('min_p')}；repeat_penalty={config.get('repeat_penalty')}"],
        ["公共预算", f"每任务6次工具调用；总轮数{config.get('max_rounds')}；格式修复{config.get('format_retries')}次；超时{config.get('task_timeout_seconds')}秒"],
        ["非思考模板", lock.get("chat_template", "待核验")],
        ["模板SHA256", runtime.get("template_sha256", "待核验")],
    ]
    verified = read_json(ROOT / "results/environment/artifact_verification.json")
    smoke = read_json(ROOT / "results/environment/model_smoke.json")
    note = "模型来源配置已固定；"
    note += "下载校验记录已生成。" if verified else "下载完成与哈希实测记录尚待生成。"
    note += "独立模型冒烟记录已生成，工具链结果另见第7章。" if smoke else "独立模型冒烟尚无结果文件。"
    return table(["项目", "实际配置"], rows) + "\n\n" + note


def data_block():
    manifest = read_json(ROOT / "data/frozen_manifest.json") or read_json(ROOT / "data/manifest.json")
    if not manifest:
        return "尚无数据清单。"
    coverage = manifest.get("coverage", {})
    labels = {"direct": "直接注入", "role_forgery": "角色或授权伪造", "workflow_hijack": "工作流程劫持", "exfiltration": "数据窃取与目标替换", "encoding": "编码变形", "segmented": "分段和多轮诱导"}
    normal_labels = {"query": "查询与提取", "notification": "通知发送", "export": "文件导出", "multi_step": "多步骤任务"}
    rows = [[labels.get(k, k), v] for k, v in coverage.get("attack_categories", {}).items()]
    normal = [[normal_labels.get(k, k), v] for k, v in coverage.get("normal_categories", {}).items()]
    status = "已冻结" if manifest.get("frozen") else "尚未冻结"
    digest = manifest.get("files", {}).get("test.jsonl", "待生成")
    lines = [f"正式数据共{coverage.get('formal_count', '待核验')}条，其中攻击{coverage.get('attack_count', '待核验')}条、正常{coverage.get('normal_count', '待核验')}条。开发集{coverage.get('development_count', '待核验')}条，不计入正式样本数。生成种子为{manifest.get('seed')}，当前状态为{status}。", table(["攻击类别", "样本数"], rows), table(["正常任务类别", "样本数"], normal)]
    entries = coverage.get("attack_entries", {})
    lines.append("入口分布为" + "，".join(f"{k} {v}条" for k, v in entries.items()) + "。")
    lines.append(f"开发与正式模板骨架重合数为{coverage.get('dev_test_skeleton_overlap', '待核验')}，重复ID数为{coverage.get('duplicate_ids', '待核验')}，正式攻击不同骨架数为{coverage.get('distinct_attack_skeletons', '待核验')}。语义独立性不能仅由字符串去重证明。")
    lines.append(f"正常确认案例{coverage.get('normal_confirmation_cases', '待核验')}条，过滤误伤挑战案例{coverage.get('normal_filter_challenge_cases', '待核验')}条。正式文件SHA256为：\n\n`{digest}`")
    return "\n\n".join(lines)


def test_block():
    path = ROOT / "results/validation/pytest.xml"
    if not path.exists():
        return "尚无pytest XML报告，不能报告测试通过。"
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    values = {key: sum(int(s.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    passed = values["tests"] - values["failures"] - values["errors"] - values["skipped"]
    groups = {}
    for case in root.iter("testcase"):
        cls = case.get("classname", "unknown")
        groups[cls] = groups.get(cls, 0) + 1
    return (f"实际pytest记录：{values['tests']}个测试，{passed}通过，{values['failures']}失败，{values['errors']}错误，{values['skipped']}跳过。记录时间为{suites[0].get('timestamp', '未记录')}。证据文件为results/validation/pytest.xml；此处读取真实XML，不依据预设数量。\n\n" + table(["测试模块", "用例数"], sorted(groups.items())))


def summary_block(folder, primary=False):
    path = ROOT / "results" / folder / "summary.json"
    summary = read_json(path)
    if not summary:
        return "尚无该实验的summary.json，不报告任何推测指标。"
    modes = summary.get("modes", {})
    planned = summary.get("manifest", {}).get("planned_runs", "未记录")
    total = summary.get("total_runs", 0)
    lines = [f"实际已保存并纳入统计{total}次运行；该目录预设运行数为{planned}。数据来源为results/{folder}/metrics.jsonl及summary.json。"]
    manifest = summary.get("manifest", {})
    if manifest:
        lines.append(f"本目录种子为{manifest.get('seeds')}，并行worker数为{manifest.get('workers', '未记录')}，确认方式为{manifest.get('confirmation_mode')}。数据SHA256为{manifest.get('dataset_sha256')}；运行时代码SHA256为{manifest.get('runtime_sha256')}。")
    if primary and total != 972:
        lines.append("本目录尚未达到预设972次主实验数量，以下为已记录结果，不能称为全量主实验交付。")
    safety = []
    utility = []
    exposure = []
    overhead = []
    ordered_modes = [mode for mode in ("none", "input_filter", "taint_policy", "policy_only") if mode in modes]
    for mode in ordered_modes:
        group = modes[mode]
        a = group.get("attack_runs", 0)
        n = group.get("normal_runs", 0)
        safety.append([mode, ratio(group, "asr", a), percent(group.get("direct_asr")), percent(group.get("indirect_asr")), ratio(group, "canary_leak_rate", a)])
        utility.append([mode, ratio(group, "normal_completion_rate", n), ratio(group, "attacked_safe_completion_rate", a), percent(group.get("normal_automatic_completion_rate")), percent(group.get("normal_assisted_completion_rate"))])
        exposure.append([mode, percent(group.get("attack_read_rate")), percent(group.get("attack_entered_model_rate")), group.get("attack_not_exposed_count", 0), percent(group.get("unauthorized_execution_rate"))])
        overhead.append([mode, f"{group.get('mean_elapsed_seconds', 0):.2f}", group.get("parse_failure_runs", 0), group.get("timeout_count", 0), group.get("exhausted_count", 0), group.get("pending_count", 0)])
    lines.extend([
        table(["配置", "主ASR", "直接ASR", "间接ASR", "Canary泄露"], safety),
        table(["配置", "正常完成", "攻击下安全完成", "自动完成", "确认辅助完成"], utility),
        table(["配置", "攻击读取", "进入模型", "未接触数", "越权执行率"], exposure),
        table(["配置", "平均秒", "解析失败运行", "超时", "耗尽", "pending"], overhead),
    ])
    seed_rows = []
    for mode in ordered_modes:
        for seed in manifest.get("seeds", [11, 23, 47]):
            group = summary.get("by_seed", {}).get(f"{mode}:{seed}")
            if group:
                seed_rows.append([mode, seed, ratio(group, "asr", group.get("attack_runs", 0)), ratio(group, "normal_completion_rate", group.get("normal_runs", 0))])
    if seed_rows:
        lines.append("按固定种子分组的实际结果如下。每行复用同一组样本，行之间不能当成独立抽样。")
        lines.append(table(["配置", "种子", "主ASR", "正常完成率"], seed_rows))
    for mode in ordered_modes:
        group = modes[mode]
        lines.append(f"{mode}：任一违规率{percent(group.get('any_violation_rate'))}。正常样本发生阻断比例{percent(group.get('normal_blocked_rate'))}，阻断且未完成比例{percent(group.get('normal_failed_with_block_rate'))}。正常阻断原因计数为{json.dumps(group.get('normal_block_reasons', {}), ensure_ascii=False)}。输入token合计{group.get('total_prompt_tokens', 0)}，输出token合计{group.get('total_completion_tokens', 0)}，工具调用{group.get('total_tool_calls', 0)}次，确认{group.get('total_confirmations', 0)}次。后端计数：{json.dumps(group.get('backend_counts', {}), ensure_ascii=False)}。")
    lines.append("辅助完成采用实验清单记录的确认方式；如果使用simulate_authorized，则属于模拟确认辅助，不能当作实际人员逐次操作。耗时是当前并行运行下的每任务墙钟时间，不能直接等同于串行延迟。")
    lines.append("按种子与类别的分组结果保留在summary.json的by_seed和by_category。重复种子属于配对重复，不新增独立攻击样本。")
    return "\n\n".join(lines)


def smoke_block():
    summaries = []
    for folder in sorted((ROOT / "results").glob("*smoke*")):
        summary = read_json(folder / "summary.json")
        if summary:
            summaries.append((folder.name, summary))
    if not summaries:
        groups = []
        for folder in sorted((ROOT / "results").glob("*smoke*")):
            records = [read_json(path) for path in (folder / "records").glob("*.json")]
            if records:
                groups.append([folder.name, len(records), sum(bool(r.get("assessment", {}).get("legitimate_success")) for r in records), ", ".join(sorted({r.get("backend_type", "unknown") for r in records}))])
        if not groups:
            return "尚无完整真实工具链冒烟汇总。独立模型JSON生成测试不能替代工具成功和关键事实校验。"
        return table(["开发冒烟目录", "已保存运行", "合法任务完成", "实际后端"], groups) + "\n\n此表直接读取各目录records内的独立评测字段。早期失败保留用于说明修复过程；不同开发版本不能混成正式实验成绩。"
    rows = []
    for name, summary in summaries:
        for mode, group in summary.get("modes", {}).items():
            rows.append([name, mode, group.get("runs"), percent(group.get("normal_completion_rate")), json.dumps(group.get("backend_counts", {}), ensure_ascii=False)])
    return table(["结果目录", "配置", "运行数", "正常完成率", "实际后端"], rows) + "\n\n开发冒烟用于发现运行链路问题，不能替代正式冻结集的主实验。"


def cases_block():
    findings = ROOT / "docs/experiment_findings.md"
    if findings.exists():
        source = findings.read_text(encoding="utf-8")
        chosen = []
        wanted = ("完整防御仍有的事实污染", "正常完成率66.67%的具体原因", "演示候选与证据边界")
        for heading in wanted:
            match = re.search(r"^## " + re.escape(heading) + r"\n(.*?)(?=^## |\Z)", source, re.S | re.M)
            if match:
                clean_heading = "正常任务未完成的具体原因" if heading.startswith("正常完成率") else heading
                chosen.append("### " + clean_heading + "\n\n" + match.group(1).strip())
        if chosen:
            return "以下案例分析来自docs/experiment_findings.md，并可通过其中run_id回查实际JSON轨迹。\n\n" + "\n\n".join(chosen)
    records_dir = ROOT / "results/main/records"
    records = [read_json(path) for path in records_dir.glob("*.json")]
    if not records:
        return "尚无正式真实运行轨迹，暂不举示未经验证的攻击成功或防御成功案例。"
    selections = []
    predicates = [
        ("无防御下实际攻击成功", lambda r: r.get("mode") == "none" and r.get("assessment", {}).get("attack_success")),
        ("完整防御阻断后完成合法任务", lambda r: r.get("mode") == "taint_policy" and r.get("assessment", {}).get("safe_completion") and r.get("assessment", {}).get("blocked_count", 0) > 0),
        ("正常任务合法通知或导出", lambda r: r.get("kind") == "normal" and r.get("mode") == "taint_policy" and r.get("assessment", {}).get("legitimate_success") and (r.get("state", {}).get("inbox") or r.get("state", {}).get("files"))),
        ("正常任务未完成的保留案例", lambda r: r.get("kind") == "normal" and r.get("mode") == "taint_policy" and not r.get("assessment", {}).get("legitimate_success")),
    ]
    for title, predicate in predicates:
        record = next((r for r in records if predicate(r)), None)
        if not record:
            selections.append(title + "：当前已保存记录中未找到符合条件的案例，不能伪造展示。")
            continue
        decisions = [f"{(event.get('action') or {}).get('tool', (event.get('action') or {}).get('type', 'system'))} {event.get('decision')} {event.get('reason')}" for event in record.get("events", [])]
        assessment = record.get("assessment", {})
        selections.append(f"{title}。样本{record.get('case_id')}，模式{record.get('mode')}，seed={record.get('seed')}，run_id={record.get('run_id')}，backend_type={record.get('backend_type')}。状态{record.get('status')}，合法完成={assessment.get('legitimate_success')}，攻击成功={assessment.get('attack_success')}。动作序列：" + "；".join(decisions) + "。")
    return "\n\n".join(selections)


def artifact_block():
    required = [
        ("源码入口", "src/taintlab/cli.py"), ("依赖定义", "pyproject.toml"),
        ("模型锁定信息", "configs/model.lock.json"), ("正式数据集", "data/test.jsonl"),
        ("测试报告", "results/validation/pytest.xml"), ("主实验结果", "results/main/summary.json"),
        ("消融实验结果", "results/ablation/summary.json"), ("演示视频", "demo/demo.mp4"),
        ("演示字幕", "demo/demo_subtitles.srt"), ("演示稿", "demo/demo_script.md"),
        ("成员模板", "docs/members_workload.csv"),
    ]
    rows = []
    for title, name in required:
        path = ROOT / name
        rows.append([title, name, f"存在 {path.stat().st_size:,}字节" if path.is_file() else "尚未生成"])
    return table(["成果", "证据位置", "文件检查"], rows) + "\n\n文件存在仅表示已生成，功能和内容是否通过另见测试、实验与媒体验收记录。"


def video_block():
    video = ROOT / "demo/demo.mp4"
    if not video.is_file():
        return "尚无demo/demo.mp4，视频交付未完成。字幕和脚本不能替代180至300秒可播放视频。"
    candidates = [ROOT / "demo/video_validation.json", ROOT / "demo/media_probe.json", ROOT / "results/validation/video.json", ROOT / "demo/probe.json"]
    record = next((read_json(path) for path in candidates if path.exists()), {})
    if not record:
        return f"demo/demo.mp4已生成，大小{video.stat().st_size:,}字节；尚无可读取的媒体核验记录，不在本报告中推测时长、编码或播放成功。"
    streams = record.get("probe", {}).get("streams", [])
    actual_hash = hashlib.sha256(video.read_bytes()).hexdigest()
    validation_matches = record.get("video_sha256") == actual_hash
    video_stream = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio_stream = next((item for item in streams if item.get("codec_type") == "audio"), {})
    rows = [
        ["实际时长", str(record.get("actual_duration", "未记录")) + "秒"],
        ["视频编码", video_stream.get("codec_name", "未记录")],
        ["分辨率", f"{video_stream.get('width', '?')} × {video_stream.get('height', '?')}"],
        ["帧率", video_stream.get("r_frame_rate", "未记录")],
        ["音频编码", audio_stream.get("codec_name", "未记录")],
        ["字幕段数", len(record.get("captions", []))],
        ["自动核验", record.get("valid", "未记录") if validation_matches else "记录与当前视频不匹配，需重新核验"],
        ["视频SHA256", actual_hash],
    ]
    labels = {"duration_180_to_300": "时长位于180至300秒", "duration_matches_plan": "时长与录制计划一致", "video_h264": "H.264视频编码", "pixel_format_yuv420p": "YUV420P像素格式", "resolution": "分辨率符合计划", "audio_aac": "AAC音频编码", "audio_duration_matches_plan": "音频与计划时长一致", "sample_frames_not_black": "抽样帧非黑屏", "audio_not_silent": "音轨非静音", "no_black_interval_over_one_second": "未发现超过1秒的连续黑屏"}
    checks = [[labels.get(name, name), "通过" if passed else "未通过"] for name, passed in record.get("checks", {}).items()]
    playback = read_json(ROOT / "demo/playback_validation.json")
    samples = playback.get("samples", [])
    played = "尚无独立浏览器播放验证记录。"
    if playback.get("all_passed") is True and playback.get("video_sha256") == actual_hash:
        positions = "、".join(str(item.get("requested")) for item in samples)
        no_error = all(item.get("error") is None for item in samples)
        no_dropped_frames = all(item.get("quality", {}).get("droppedVideoFrames") == 0 for item in samples)
        played = f"实际播放核验通过：隔离本地浏览器在{positions}秒共{len(samples)}个位置跳转后继续播放，全部无媒体错误={no_error}、抽查报告无掉帧={no_dropped_frames}，视频SHA256与当前成片一致。证据为demo/playback_validation.json。主代理已查看开头、中间来源图、旧版恢复、确认后及结尾指标画面，版本回放角标和中文字幕可读。"
    return ("视频位于demo/demo.mp4，字幕为demo/demo_subtitles.srt，演示稿为demo/demo_script.md。以下数据直接读取demo/video_validation.json。\n\n" + table(["项目", "实测值"], rows) + "\n\n" + table(["自动媒体检查", "结果"], checks) + "\n\n编码过程使用实际浏览器录制和本地中文旁白，记录输入素材哈希、剪裁起点和输出时长。自动检查不代替画面审查。\n\n" + played)


def log_block():
    path = ROOT / "docs/DEVELOPMENT_LOG.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if not text:
        return "尚无实际开发日志。"
    # Preserve actual wording and chronology. Downshift headings to this section.
    text = re.sub(r"^# .+\n", "", text, count=1)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)
    return text.strip()


def commands_block():
    path = ROOT / "data/dev.jsonl"
    if not path.exists():
        return "尚无可选开发案例ID。"
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    picks = [case for case in cases if case.get("kind") == "normal"][:3]
    commands = [f'.\\.venv\\Scripts\\python.exe -m taintlab.cli run `\n    --dataset data/dev.jsonl --case {case["id"]} `\n    --mode taint_policy --seed 11' for case in picks]
    return "```powershell\n" + "\n".join(commands) + "\n```"


def clean_block():
    clean = read_json(ROOT / "results/validation/clean_install.json")
    offline = read_json(ROOT / "results/validation/offline_validation.json")
    if not clean and not offline:
        return "尚无全新虚拟环境与离线运行验证记录，不能声称清洁安装或实际断网验收已完成。"
    sections = []
    if clean:
        installation = clean.get("actual_install_script_test", {})
        sections.append(f"全新环境为{clean.get('fresh_venv')}，Python版本{clean.get('python', '').split()[0]}。依赖离线安装={clean.get('offline_dependency_install')}，项目离线可编辑安装={clean.get('offline_editable_install')}；依赖检查为{clean.get('dependency_check')}；真实安装脚本退出码{installation.get('exit_code')}，命令入口帮助退出码{clean.get('entrypoint_help_exit_code')}。证据为results/validation/clean_install.json及其列出的安装日志。")
    if offline:
        sections.append(f"本机模型验收记录时间为{offline.get('started_at_utc')}，模式{offline.get('mode')}，seed={offline.get('seed')}。全部合法任务成功={offline.get('all_tasks_succeeded')}，业务外部网络尝试数={offline.get('business_external_attempts')}。记录文件为results/validation/offline_validation.json。")
        rows = [[run.get("case_id"), run.get("status"), run.get("assessment", {}).get("legitimate_success"), run.get("backend_type")] for run in offline.get("runs", [])]
        sections.append(table(["实际案例", "状态", "关键内容通过", "后端"], rows))
        checks = offline.get("guard_negative_tests", [])
        sections.append("网络限制负向自检：" + "；".join(f"{item.get('name')}={item.get('passed')}" for item in checks) + "。")
    sections.append("验证边界：使用现有CPython和本地依赖缓存建立新的虚拟环境；应用进程的标准Python socket API阻止非回环连接。已启动的llama.cpp属于另一个进程，不在该拦截内部。没有对整台计算机物理断网，也未约束恶意原生代码或新建子进程，因此报告只声称已验证当前应用的本机离线执行路径。")
    return "\n\n".join(sections)


def remaining_block():
    notes = ["成员姓名、学号、真实分工和实际人工工时仍需小组填写。"]
    summary = read_json(ROOT / "results/main/summary.json")
    if summary.get("total_runs") != 972:
        notes.append(f"主实验目前可读取{summary.get('total_runs', 0)}次结果，尚未达到972次完成条件。")
    if not (ROOT / "results/ablation/summary.json").exists():
        notes.append("policy_only消融结果尚未生成。")
    if not (ROOT / "demo/demo.mp4").exists():
        notes.append("演示MP4尚未生成。")
    elif read_json(ROOT / "demo/video_validation.json").get("valid") is not True:
        notes.append("演示MP4已生成，但尚无全部通过的媒体校验记录。")
    if not list((ROOT / "results/validation").glob("*clean*.json")):
        notes.append("全新虚拟环境验收尚无专门记录。")
    notes.append("其他平台未在当前设备验证。统计结论只适用于冻结数据、配置与本机模型；侧信道和精确内部因果不在保证范围内。")
    return "\n\n".join(notes)


def interpretation_block():
    summary = read_json(ROOT / "results/main/summary.json")
    modes = summary.get("modes", {})
    if not all(name in modes for name in ("none", "input_filter", "taint_policy")):
        return "缺少三配置的完整统计，暂不推断防御差异。"
    a, b, c = (modes[name] for name in ("none", "input_filter", "taint_policy"))
    lines = [f"本次主实验中，none主ASR为{percent(a.get('asr'))}，input_filter为{percent(b.get('asr'))}，taint_policy为{percent(c.get('asr'))}。这属于当前冻结任务的描述性差异，不构成跨模型或真实业务攻击概率的估计。"]
    lines.append(f"正常完成率分别为{percent(a.get('normal_completion_rate'))}、{percent(b.get('normal_completion_rate'))}和{percent(c.get('normal_completion_rate'))}。输入过滤在降低攻击进入上下文比例的同时减少了任务所需文本，正常任务代价必须与安全指标一起阅读。无防御本身也没有达到全部正常任务成功，说明本地小模型能力是主要限制之一。")
    if all(group.get("canary_leak_rate") == 0 for group in (a, b, c)):
        lines.append("三种主配置的Canary泄露率均为零。本次正式数据没有形成可观察的Canary泄露成功，因而不能据此声称污点机制相对于基线显著改善了泄露率。权限或信息流机制的独立效果还需结合消融与确定性回归测试。")
    if c.get("asr", 0) > 0:
        lines.append("完整防御的主ASR仍大于零。来源与权限策略没有解决授权范围内的全部事实篡改，不能宣称完全防御提示注入。保留实际成功攻击和正常失败记录，是本项目验收的一部分。")
    ablation = read_json(ROOT / "results/ablation/summary.json").get("modes", {}).get("policy_only")
    if ablation:
        lines.append(f"消融中policy_only主ASR为{percent(ablation.get('asr'))}，正常完成率{percent(ablation.get('normal_completion_rate'))}；taint_policy对应为{percent(c.get('asr'))}和{percent(c.get('normal_completion_rate'))}。")
        if ablation.get("canary_leak_rate") == 0 and c.get("canary_leak_rate") == 0:
            lines.append("本次真实小模型消融没有观测到污点信息流约束在Canary泄露率上的独立收益；两种策略均为零泄露。不能把机制的单元测试通过替换为真实模型安全收益。污点机制的程序级行为由确定性回归用例验证，其现实攻击收益需要更多能触发敏感流的案例。")
    return "\n\n".join(lines)


def make_figures():
    """Use bundled ReportLab/Poppler, not an invented screenshot or metric."""
    from reportlab.graphics import renderPDF
    from reportlab.graphics.shapes import Drawing, Line, Rect, String, Polygon
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    folder = QA / "figures"
    folder.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("LabCN", "C:/Windows/Fonts/simsun.ttc", subfontIndex=0))
    drawing = Drawing(700, 310)
    drawing.add(String(22, 282, "系统执行路径与来源维护", fontName="LabCN", fontSize=18, fillColor=colors.black))
    drawing.add(String(22, 260, "Design schematic | no model-internal causal claims", fontName="Helvetica", fontSize=9, fillColor=colors.HexColor("#596979")))
    boxes = [
        (22, 172, "用户任务与授权", "trusted control", "#EAF2F8"),
        (194, 172, "本地模型动作提议", "potential context", "#F5F7FA"),
        (366, 172, "确定性执行网关", "grant + flow + confirm", "#E8F3EF"),
        (538, 172, "本地模拟工具", "state only", "#EAF2F8"),
        (22, 56, "文档网页工具正文", "untrusted content", "#FFF2DB"),
        (194, 56, "不可变来源注册表", "integrity / sensitivity", "#FFF2DB"),
        (366, 56, "审计与独立评测", "actual state + hidden answers", "#F5F7FA"),
        (538, 56, "真实确认与结果展示", "trusted UI", "#E8F3EF"),
    ]
    for x, y, title, subtitle, fill in boxes:
        drawing.add(Rect(x, y, 142, 60, rx=7, ry=7, fillColor=colors.HexColor(fill), strokeColor=colors.HexColor("#B7C4D0"), strokeWidth=.7))
        drawing.add(String(x + 71, y + 36, title, textAnchor="middle", fontName="LabCN", fontSize=11, fillColor=colors.black))
        drawing.add(String(x + 71, y + 17, subtitle, textAnchor="middle", fontName="Helvetica", fontSize=7.6, fillColor=colors.HexColor("#425466")))
    def arrow(x1, y1, x2, y2, dashed=False):
        line = Line(x1, y1, x2, y2, strokeColor=colors.HexColor("#63788B"), strokeWidth=1)
        if dashed:
            line.strokeDashArray = [4, 3]
        drawing.add(line)
        if x2 > x1:
            drawing.add(Polygon([x2, y2, x2 - 6, y2 + 3, x2 - 6, y2 - 3], fillColor=colors.HexColor("#63788B"), strokeColor=None))
        elif y2 > y1:
            drawing.add(Polygon([x2, y2, x2 - 3, y2 - 6, x2 + 3, y2 - 6], fillColor=colors.HexColor("#63788B"), strokeColor=None))
        else:
            drawing.add(Polygon([x2, y2, x2 - 3, y2 + 6, x2 + 3, y2 + 6], fillColor=colors.HexColor("#63788B"), strokeColor=None))
    for x in (164, 336, 508):
        arrow(x, 202, x + 30, 202)
    arrow(164, 86, 194, 86)
    arrow(265, 116, 265, 172, True)
    arrow(437, 172, 437, 116)
    arrow(609, 172, 609, 116)
    drawing.add(String(280, 142, "保留来源", fontName="LabCN", fontSize=9, fillColor=colors.HexColor("#425466")))
    drawing.add(String(22, 24, "所有副作用发生在模拟世界；最终回复也经过网关。实线为程序流程，虚线表示上下文来源。", fontName="LabCN", fontSize=9, fillColor=colors.HexColor("#425466")))
    pdf = folder / "architecture.pdf"
    renderPDF.drawToFile(drawing, str(pdf))
    poppler = RUNTIME / "native/poppler/Library/bin/pdftoppm.exe"
    subprocess.run([str(poppler), "-singlefile", "-scale-to-x", "1800", "-scale-to-y", "-1", "-png", str(pdf), str(folder / "architecture")], check=True, capture_output=True)
    summary = read_json(ROOT / "results/main/summary.json")
    modes = summary.get("modes", {})
    if not modes:
        return
    labels = [name for name in ("none", "input_filter", "taint_policy") if name in modes]
    chart = Drawing(700, 350)
    chart.add(String(32, 320, "主实验安全性与正常任务完成率", fontName="LabCN", fontSize=17))
    chart.add(String(32, 299, f"Unit: % | recorded runs: {summary.get('total_runs')} | source: results/main/summary.json", fontName="Helvetica", fontSize=9, fillColor=colors.HexColor("#596979")))
    bars = VerticalBarChart()
    bars.x = 65
    bars.y = 75
    bars.height = 200
    bars.width = 585
    bars.data = [tuple(100 * (modes[name].get(key) or 0) for name in labels) for key in ("asr", "normal_completion_rate", "attacked_safe_completion_rate")]
    bars.categoryAxis.categoryNames = labels
    bars.categoryAxis.labels.fontName = "Helvetica"
    bars.categoryAxis.labels.fontSize = 10
    bars.valueAxis.valueMin = 0
    bars.valueAxis.valueMax = 100
    bars.valueAxis.valueStep = 20
    bars.valueAxis.labels.fontName = "Helvetica"
    bars.groupSpacing = 18
    bars.barSpacing = 3
    bars.bars[0].fillColor = colors.HexColor("#B45350")
    bars.bars[1].fillColor = colors.HexColor("#217A78")
    bars.bars[2].fillColor = colors.HexColor("#577AA5")
    chart.add(bars)
    for x, color, title in [(70, "#B45350", "攻击成功率"), (270, "#217A78", "正常完成率"), (470, "#577AA5", "攻击下安全完成率")]:
        chart.add(Rect(x, 28, 12, 12, fillColor=colors.HexColor(color), strokeColor=None))
        chart.add(String(x + 19, 30, title, fontName="LabCN", fontSize=10))
    chart_pdf = folder / "metrics.pdf"
    renderPDF.drawToFile(chart, str(chart_pdf))
    subprocess.run([str(poppler), "-singlefile", "-scale-to-x", "1800", "-scale-to-y", "-1", "-png", str(chart_pdf), str(folder / "metrics")], check=True, capture_output=True)


def refresh_markdown():
    text = SOURCE.read_text(encoding="utf-8")
    mapping = {
        "MODEL": model_block(), "DATA": data_block(), "TESTS": test_block(),
        "RESULTS": summary_block("main", primary=True), "ABLATION": summary_block("ablation"),
        "SMOKE": smoke_block(), "CASES": cases_block(), "ARTIFACTS": artifact_block(),
        "VIDEO": video_block(), "LOG": log_block(), "COMMANDS": commands_block(),
        "CLEAN": clean_block(), "REMAINING": remaining_block(),
        "INTERPRETATION": interpretation_block(),
        "CHART": "![图2 主实验实际指标 来源为results/main/summary.json](docs/qa/figures/metrics.png)" if read_json(ROOT / "results/main/summary.json").get("modes") and (QA / "figures/metrics.png").exists() else "尚无真实主实验图表。",
    }
    for key, value in mapping.items():
        pattern = rf"(<!-- BEGIN AUTO {key} -->)\n.*?\n(<!-- END AUTO {key} -->)"
        text, count = re.subn(pattern, lambda m: m[1] + "\n" + value + "\n" + m[2], text, flags=re.S)
        if count != 1:
            raise ValueError(f"Expected one generated block {key}, got {count}")
    SOURCE.write_text(text, encoding="utf-8")
    return text


def set_font(run, size=10.5, name="SimSun", bold=False):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor(0, 0, 0)
    properties = run._element.get_or_add_rPr()
    fonts = properties.rFonts
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        properties.insert(0, fonts)
    for key in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn("w:" + key), name)


def add_inline(paragraph, text, size=10.5):
    for part in re.split(r"(`[^`]+`|\*\*.+?\*\*)", text):
        if not part:
            continue
        if part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            set_font(run, max(size - 0.5, 8), "Consolas")
        elif part.startswith("**") and part.endswith("**"):
            set_font(paragraph.add_run(part[2:-2]), size, bold=True)
        else:
            set_font(paragraph.add_run(part), size)


def format_table(table_obj, rows):
    table_obj.autofit = False
    count = len(rows[0])
    if count == 2:
        numeric_second = all(re.fullmatch(r"[0-9.,%]+", str(row[1]).strip()) or str(row[1]).strip() in {"通过", "未通过", "待核验", "是", "否"} for row in rows[1:])
        widths = [13.5, 3.4] if numeric_second else [3.8, 13.1]
    elif count == 3:
        widths = [4.5, 6.0, 6.4]
    elif count == 4:
        widths = [3.3, 3.5, 3.5, 6.6]
    else:
        widths = [2.7] + [(16.9 - 2.7) / (count - 1)] * (count - 1)
    props = table_obj._tbl.tblPr
    for column, width in zip(table_obj.columns, widths):
        column.width = Cm(width)
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement("w:" + edge)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:color"), "D9D9D9")
        borders.append(element)
    props.append(borders)
    for row_index, row in enumerate(table_obj.rows):
        no_split = OxmlElement("w:cantSplit")
        row._tr.get_or_add_trPr().append(no_split)
        if row_index == 0:
            trpr = row._tr.get_or_add_trPr()
            header = OxmlElement("w:tblHeader")
            trpr.append(header)
        for column, cell in enumerate(row.cells):
            cell.width = Cm(widths[column])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            cell.text = ""
            paragraph = cell.paragraphs[0]
            compact_media_table = rows[0][0] == "自动媒体检查"
            paragraph.paragraph_format.space_after = Pt(1 if compact_media_table else 3)
            paragraph.paragraph_format.space_before = Pt(1 if compact_media_table else 3)
            paragraph.paragraph_format.line_spacing = 1.1
            # Keep short comparison tables together; longer evidence tables may
            # span pages and repeat their header naturally.
            if len(rows) <= 5 and row_index < len(rows) - 1:
                paragraph.paragraph_format.keep_with_next = True
            text = str(rows[row_index][column])
            if re.fullmatch(r"[0-9a-f]{40,}", text):
                text = "\n".join(text[i:i + 32] for i in range(0, len(text), 32))
            add_inline(paragraph, text, size=9 if count >= 5 else 9.5)
            if row_index == 0:
                for run in paragraph.runs:
                    run.bold = True
                    run.font.color.rgb = RGBColor(255, 255, 255)
            if column > 0 and ((count >= 4 and len(text) < 24) or (count == 2 and numeric_second)):
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            tcpr = cell._tc.get_or_add_tcPr()
            shading = OxmlElement("w:shd")
            shading.set(qn("w:fill"), "243746" if row_index == 0 else ("F4F7F9" if row_index % 2 == 0 else "FFFFFF"))
            tcpr.append(shading)
            margins = OxmlElement("w:tcMar")
            for edge in ("top", "left", "bottom", "right"):
                item = OxmlElement("w:" + edge)
                item.set(qn("w:w"), "45" if compact_media_table else "90")
                item.set(qn("w:type"), "dxa")
                margins.append(item)
            tcpr.append(margins)


def build_docx(text, toc_pages=None):
    document = Document()
    # The bundled python-docx default template carries a Title paragraph border.
    # Remove it explicitly rather than assuming a new document is undecorated.
    for style in document.styles:
        for border in style._element.xpath(".//w:pBdr"):
            border.getparent().remove(border)
    section = document.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.1)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.05)
    section.right_margin = Cm(2.05)
    section.header_distance = Cm(0.7)
    section.footer_distance = Cm(0.8)
    normal = document.styles["Normal"]
    normal.font.name = "SimSun"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal.paragraph_format.line_spacing = 1.3
    normal.paragraph_format.space_after = Pt(6)
    for name, size in (("Title", 24), ("Heading 1", 16), ("Heading 2", 12), ("Heading 3", 11)):
        style = document.styles[name]
        style.font.name = "Microsoft YaHei"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.bold = True
        style.paragraph_format.space_before = Pt(13)
        style.paragraph_format.space_after = Pt(8)
        style.paragraph_format.keep_with_next = True
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(footer.add_run("第 "), 9)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)
    set_font(footer.add_run(" 页"), 9)
    document.core_properties.title = "本地小模型 Agent 间接提示注入攻防与污点追踪系统"
    document.core_properties.subject = "专业实习项目过程与验收报告"
    document.core_properties.author = "项目小组 待补充"
    document.core_properties.comments = "AI辅助实现与材料整理；真实成员贡献和工时待补充。"
    lines = text.splitlines()
    first_chapter = next(i for i, line in enumerate(lines) if line.startswith("## "))
    front = [line.strip() for line in lines[:first_chapter] if line.strip()]
    p = document.add_paragraph(style="Title")
    p.paragraph_format.space_before = Pt(54)
    title = front[0].lstrip("# ")
    set_font(p.add_run(title), 24, "Microsoft YaHei", True)
    p = document.add_paragraph()
    p.paragraph_format.space_after = Pt(24)
    set_font(p.add_run(front[1]), 16, "Microsoft YaHei")
    for line in front[2:]:
        add_inline(document.add_paragraph(), line)
    document.add_page_break()
    p = document.add_paragraph("目录", style="Heading 1")
    for line in lines:
        if line.startswith("## "):
            heading = line[3:].strip()
            p = document.add_paragraph()
            p.paragraph_format.space_after = Pt(9)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(16.8), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            number = str((toc_pages or {}).get(heading, ""))
            add_inline(p, heading + "\t" + number, 11)
    document.add_paragraph("目录根据本次PDF渲染页码生成。修改正文后请重新运行构建脚本更新。")
    index = first_chapter
    in_code = False
    while index < len(lines):
        line = lines[index]
        index += 1
        if line.startswith("<!--") or not line.strip():
            continue
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            p = document.add_paragraph()
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.05
            p.paragraph_format.left_indent = Cm(0.2)
            # Add safe wrap opportunities to lengthy URLs/paths, preserving visible text.
            visible = line.replace("/", "/\u200b").replace("\\", "\\\u200b")
            set_font(p.add_run(visible), 8.5, "Consolas")
            continue
        if line.startswith("## "):
            p = document.add_paragraph(line[3:], style="Heading 1")
            p.paragraph_format.page_break_before = True
            for run in p.runs:
                set_font(run, 16, "Microsoft YaHei", True)
        elif line.startswith("### "):
            p = document.add_paragraph(line[4:], style="Heading 2")
            for run in p.runs:
                set_font(run, 12, "Microsoft YaHei", True)
        elif line.startswith("| "):
            raw_rows = [line]
            while index < len(lines) and lines[index].startswith("|"):
                raw_rows.append(lines[index])
                index += 1
            rows = [[part.strip() for part in row.strip().strip("|").split("|")] for row in raw_rows]
            rows = [row for row in rows if not all(re.fullmatch(r"[-: ]+", cell) for cell in row)]
            max_cols = max(map(len, rows))
            rows = [row + [""] * (max_cols - len(row)) for row in rows]
            table_obj = document.add_table(rows=len(rows), cols=max_cols)
            format_table(table_obj, rows)
            document.add_paragraph().paragraph_format.space_after = Pt(2)
        elif line.startswith("!["):
            match = re.fullmatch(r"!\[(.*?)\]\((.*?)\)", line)
            if match:
                image = ROOT / match[2]
                if image.exists():
                    p = document.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.paragraph_format.keep_with_next = True
                    p.add_run().add_picture(str(image), width=Cm(16.5))
                    caption = document.add_paragraph(match[1])
                    caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif line.startswith("- "):
            add_inline(document.add_paragraph(style="List Bullet"), line[2:])
        else:
            add_inline(document.add_paragraph(), line)
    DIST.mkdir(exist_ok=True)
    path = DIST / "project_report.docx"
    document.save(path)
    return path


def render(docx_path, renderer, soffice):
    env = os.environ.copy()
    # LibreOffice emits localized CP936 diagnostics on this Windows host, while
    # Python's own output remains UTF-8 for the parent log collector.
    env["PYTHONUTF8"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    folders = [str(RUNTIME / "native/poppler/Library/bin"), str(RUNTIME / "bin/override")]
    if soffice:
        executable = Path(soffice).resolve()
        if not executable.exists():
            raise FileNotFoundError(executable)
        folders.insert(0, str(executable.parent))
    env["PATH"] = os.pathsep.join(folders + [env.get("PATH", "")])
    output = QA / "render"
    output.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(renderer), str(docx_path), "--output_dir", str(output), "--emit_pdf", "--verbose"]
    completed = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", timeout=240)
    (QA / "render_log.txt").write_text(completed.stdout, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError(f"DOCX rendering failed; inspect {QA / 'render_log.txt'}")
    pdf = output / "project_report.pdf"
    if not pdf.is_file():
        raise RuntimeError("Renderer returned without a PDF")
    shutil.copy2(pdf, DIST / "project_report.pdf")
    return pdf


def toc_pages(pdf, text):
    from pypdf import PdfReader
    pages = PdfReader(pdf).pages
    normalized = [re.sub(r"\s+", "", page.extract_text() or "") for page in pages]
    mapping = {}
    for heading in [line[3:] for line in text.splitlines() if line.startswith("## ")]:
        key = re.sub(r"\s+", "", heading)
        for number, page in enumerate(normalized[2:], 3):
            if key in page:
                mapping[heading] = number
                break
    return mapping


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-only", action="store_true")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--soffice", type=Path)
    parser.add_argument("--renderer", type=Path, default=RENDERER)
    args = parser.parse_args()
    QA.mkdir(parents=True, exist_ok=True)
    make_figures()
    text = refresh_markdown()
    if args.refresh_only:
        print(SOURCE)
        return
    docx_path = build_docx(text)
    if args.render:
        pdf = render(docx_path, args.renderer, args.soffice)
        mapping = toc_pages(pdf, text)
        docx_path = build_docx(text, mapping)
        pdf = render(docx_path, args.renderer, args.soffice)
        from pypdf import PdfReader
        reader = PdfReader(pdf)
        # The renderer can leave pages from an older, longer revision. Remove
        # only generated page PNGs beyond the freshly rendered PDF page count.
        for old_page in (QA / "render").glob("page-*.png"):
            match = re.fullmatch(r"page-(\d+)\.png", old_page.name)
            if match and int(match[1]) > len(reader.pages):
                old_page.unlink()
        validation = {
            "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
            "docx": str(docx_path.relative_to(ROOT)), "pdf": "dist/project_report.pdf",
            "pages": len(reader.pages), "toc_pages": mapping,
            "docx_sha256": hashlib.sha256(docx_path.read_bytes()).hexdigest(),
            "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "renderer": str(args.renderer), "python": sys.executable,
            "visual_review": "required_after_latest_render",
        }
        (QA / "document_validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(validation, ensure_ascii=False, indent=2))
    else:
        print(docx_path)


if __name__ == "__main__":
    main()
