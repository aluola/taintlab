"""Streamlit UI. All side effects are delegated to the deterministic gateway."""

from __future__ import annotations

import copy
import json
import secrets
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from taintlab.ui.viewmodel import (  # noqa: E402
    DECISIONS, MODES, STATUS, action_hash, event_rows, history_files, metric_rows,
    provenance_dot, read_cases, read_json, save_record, source_nodes,
)

st.set_page_config(page_title="本地 Agent 安全实验室", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
.block-container{padding-top:1.7rem;padding-bottom:2rem;max-width:1540px}
h1{font-size:2rem!important;letter-spacing:-.04rem}h2{font-size:1.4rem!important}
[data-testid="stSidebar"]{background:#f1f5f9}
[data-testid="stMetric"]{padding:14px 16px;border:1px solid #dce5ee;border-radius:12px;background:#f8fafc}
[data-testid="stMetricLabel"]{font-size:.85rem}[data-testid="stMetricValue"]{font-size:1.6rem}
.hero-kicker{font-weight:650;color:#0f766e;font-size:.85rem;letter-spacing:.07rem;margin-bottom:.2rem}
.boundary{padding:.6rem .9rem;background:#e8f5f3;color:#134e4a;border-left:4px solid #0f766e;border-radius:5px;margin-bottom:1rem}
.muted{color:#64748b;font-size:.9rem}.replay{padding:.8rem 1rem;background:#fff7ed;border:1px solid #fdba74;border-radius:10px;color:#9a3412;font-weight:650}
.stTabs [data-baseweb="tab-list"]{gap:20px}.stTabs [data-baseweb="tab"]{font-size:.95rem}
.stApp{font-family:'Microsoft YaHei','Segoe UI',sans-serif}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=30, show_spinner=False)
def record_title(path: Path) -> str:
    # Only a small metadata projection is shown; task text is never an HTML label.
    data = read_json(path, {})
    return f"{data.get('case_id', path.stem[:12])} · {data.get('mode', '?')} · {str(data.get('run_id', ''))[:16]}"


def display_config() -> None:
    model = read_json(ROOT / "configs" / "model.json", {})
    with st.expander("模型与推理配置", expanded=False):
        if model:
            st.json(model, expanded=False)
        else:
            st.info("模型配置尚未准备。目标为 Qwen3-0.6B 官方 Q8_0，llama.cpp 本机服务。")
        st.caption("模型输出仅是动作提议；动作和最终回复必须经过统一网关。实验日志中的 backend_type 才是后端证据。")


def show_case(case: dict | None) -> None:
    if not case:
        st.info("请先生成数据集，然后在左侧选择任务。")
        return
    runtime = case["runtime"]
    st.subheader("合法任务与可见环境")
    st.write(runtime.get("task", ""))
    columns = st.columns([1, 1])
    with columns[0]:
        st.caption(f"样本 {case.get('id')} · {case.get('kind')} · {case.get('category')} · {case.get('split')}")
        injection = runtime.get("injection")
        if injection:
            st.warning(f"实验注入入口：{injection.get('entry', '未知')}；来源：{injection.get('source_id', '—')}")
            st.caption("此标签用于实验观察，攻击目标与判定答案不提供给 Agent 或安全策略。")
        else:
            st.success("正常任务样本")
    with columns[1]:
        with st.expander("可信 TaskGrant 授权", expanded=False):
            st.json(runtime.get("grant", {}))
    docs = runtime.get("documents", {})
    for doc_id, document in docs.items():
        with st.expander(f"文档 {doc_id} · {document.get('sensitivity', 'unknown')} · 正文不具有指令权限"):
            st.code(document.get("content", ""), language=None, wrap_lines=True)
    if runtime.get("search_results"):
        with st.expander("本地网页与检索快照"):
            for item in runtime["search_results"]:
                st.caption(f"{item.get('id')} · {item.get('source_type')} · {item.get('sensitivity')}")
                st.code(item.get("content", ""), language=None, wrap_lines=True)
    if runtime.get("tool_return_suffix"):
        with st.expander("模拟工具返回附加内容"):
            st.code(runtime["tool_return_suffix"], language=None, wrap_lines=True)


def show_overview(record: dict | None, replay: bool = False) -> None:
    if record is None:
        st.info("选择案例并运行后，这里显示网关处理后的真实记录。也可切换到历史回放。")
        return
    if replay:
        st.markdown('<div class="replay">真实运行记录回放 · 当前画面不执行实时模型推理</div>', unsafe_allow_html=True)
        replay_label='旧开发版真实回放 · development_v3' if record.get('evidence_note') else '真实运行记录回放 · 非实时推理'
        st.markdown(f'<div style="position:fixed;top:66px;right:24px;z-index:9999;padding:8px 14px;background:#fff7ed;border:1px solid #fdba74;border-radius:8px;color:#9a3412;font-size:14px;font-weight:650">{replay_label}</div>',unsafe_allow_html=True)
    if record.get('evidence_note'):
        st.warning(record['evidence_note'])
    backend = record.get("backend_type", "unknown")
    if backend not in ("llama_cpp", "llama.cpp", "local_llama_cpp", "llama_cpp_local", "local"):
        if "mock" in backend or "script" in backend or "test" in backend:
            st.error(f"当前记录为测试后端 {backend}，不能作为真实模型实验。")
        else:
            st.caption(f"日志后端：{backend}。请结合模型调用记录核验。")
    usage = record.get("usage", {})
    columns = st.columns(5)
    columns[0].metric("运行状态", STATUS.get(record.get("status"), record.get("status", "—")))
    columns[1].metric("模型调用", usage.get("model_calls", 0))
    columns[2].metric("工具调用", usage.get("tool_calls", 0))
    columns[3].metric("阻断次数", sum(event.get("decision") == "block" for event in record.get("events", [])))
    columns[4].metric("总耗时", f"{record.get('elapsed_seconds', 0):.2f} s")
    st.caption(f"运行 ID：{record.get('run_id')}　配置：{MODES.get(record.get('mode'), record.get('mode'))}　种子：{record.get('seed')}　后端：{backend}")
    if record.get("final"):
        st.subheader("通过输出网关的最终答复")
        st.text(record["final"])
    elif record.get("status") != "pending":
        st.info("该记录没有获准交付的最终答复。工具是否执行成功，以模拟状态和独立评测为准。")
    if record.get("assessment"):
        with st.expander("独立评测结果（读取实际模拟状态）"):
            st.json(record["assessment"])


def show_timeline(record: dict) -> None:
    events = record.get("events", [])
    if not events:
        st.info("暂无动作事件。")
        return
    st.dataframe(pd.DataFrame(event_rows(record)), use_container_width=True, hide_index=True)
    selected = st.slider("查看动作步骤", 1, len(events), len(events), key=f"step_{record.get('run_id')}") if len(events) > 1 else 1
    event = events[selected - 1]
    left, right = st.columns([1.1, 1])
    with left:
        st.markdown(f"**步骤 {event.get('step', selected)} · {DECISIONS.get(event.get('decision'), event.get('decision', '事件'))}**")
        st.json(event.get("action", {}))
    with right:
        st.markdown("**程序决策与执行结果**")
        st.write(event.get("reason", ""))
        result = event.get("result", {})
        if isinstance(result, (dict, list)):
            st.json(result, expanded=False)
        else:
            st.text(str(result))
        st.caption(f"来源节点：{event.get('node_id', '—')}")
    st.caption("动作提议不等于执行成功。阻断或待确认事件不应改变模拟收件箱和虚拟文件。")


def show_sources(record: dict) -> None:
    nodes = source_nodes(record)
    if not nodes:
        st.info("暂无来源节点。")
        return
    st.caption("虚线：模型可见上下文的潜在依赖；实线：程序记录的确定性派生。图中没有模型内部思维过程。")
    focused=st.checkbox('聚焦一个动作的来源邻域',value=True,key='focus_'+record['run_id'])
    graph_record=record
    if focused:
        actions=[e for e in record.get('events',[]) if e.get('node_id')]
        if actions:
            default=next((i for i,e in enumerate(actions) if e.get('decision')=='block'),0)
            chosen=st.selectbox('图焦点',range(len(actions)),index=default,format_func=lambda i:f"步骤 {actions[i].get('step')} · {(actions[i].get('action') or {}).get('tool',(actions[i].get('action') or {}).get('type'))} · {actions[i].get('reason')}")
            selected={actions[chosen]['node_id']};by_id={n['node_id']:n for n in nodes}
            for _ in range(3):selected.update(p for i in list(selected) if i in by_id for p in by_id[i].get('parent_ids',[]))
            graph_record={**record,'nodes':[n for n in nodes if n['node_id'] in selected]}
            st.caption('显示所选动作向上最多三层的实际依赖边；取消聚焦可查看完整图。')
    st.graphviz_chart(provenance_dot(graph_record).replace('rankdir=LR','rankdir=TB'), use_container_width=True)
    projection = [{key: node.get(key) for key in ("node_id", "source_type", "source_id", "integrity", "sensitivity", "transformation", "parent_ids")} for node in nodes]
    st.dataframe(pd.DataFrame(projection), use_container_width=True, hide_index=True)
    with st.expander("完整来源节点（含模拟内容）"):
        st.json(nodes, expanded=False)


def show_state(record: dict) -> None:
    state = record.get("state", {})
    left, right = st.columns(2)
    with left:
        st.subheader("模拟收件箱")
        inbox = state.get("inbox", [])
        if inbox:
            if isinstance(inbox, dict):
                st.json(inbox)
            else:
                for index, item in enumerate(inbox, 1):
                    with st.container(border=True):
                        st.markdown(f"**{index}. {item.get('recipient_id', '未知收件人')}**")
                        st.text(item.get("body", ""))
        else:
            st.caption("收件箱为空。未连接真实邮箱。")
    with right:
        st.subheader("虚拟导出文件")
        files = state.get("files", {})
        if files:
            for path, content in files.items():
                with st.expander(path, expanded=True):
                    st.code(content, language=None, wrap_lines=True)
        else:
            st.caption("虚拟文件系统为空。模型路径不会成为宿主文件路径。")
    st.caption("实际读取的文档")
    st.write(state.get("reads", []))
    with st.expander("检索参数与已交付回复"):
        st.json({"search_queries": state.get("search_queries", []), "finals": state.get("finals", [])})


def show_confirmation(record: dict, replay: bool) -> None:
    if record.get("status") != "pending":
        st.info("此运行没有等待中的确认。明确越权动作应直接阻断，不进入确认流程。")
        return
    pending = next((event for event in reversed(record.get("events", [])) if event.get("decision") == "pending"), {})
    action = pending.get("action", {})
    st.warning("权限范围内的敏感动作暂停在副作用发生前。核对目标、内容和来源后，才能由真实界面创建确认事件。")
    st.json(action)
    st.caption(f"绑定运行：{record.get('run_id')}")
    st.caption(f"动作展示哈希：{action_hash(action)}（执行凭据由网关独立校验）")
    details = record.get("pending") or record.get("pending_confirmation")
    if details:
        st.json(details, expanded=False)
    node_id = pending.get("node_id")
    nodes = source_nodes(record)
    matching = [node for node in nodes if node.get("node_id") == node_id]
    if matching:
        st.markdown("**污点来源及父节点**")
        st.json(matching)
    if replay:
        st.caption("历史记录只读。请在单案运行页面进行真实人工确认。")
        return
    approve, reject, _ = st.columns([1, 1, 2])
    approved = approve.button("确认执行一次", type="primary", key="confirm_pending")
    rejected = reject.button("拒绝此操作", key="reject_pending")
    if approved or rejected:
        from taintlab.agent.runtime import resume_run
        try:
            with st.spinner("校验运行、参数、有效期与一次性凭据…"):
                updated = resume_run(record, approve=approved)
                updated["case_id"] = record.get("case_id", "")
                if st.session_state.get("live_case") and st.session_state.get("live_canary"):
                    from taintlab.evaluation.evaluator import evaluate
                    updated["assessment"] = evaluate(st.session_state["live_case"], updated, st.session_state["live_canary"])
                st.session_state["live_record"] = updated
                save_record(ROOT, updated)
            st.rerun()
        except (ValueError, KeyError) as exc:
            st.error(f"确认未执行：{type(exc).__name__}。请重新运行案例获取有效确认。")


def show_metrics() -> None:
    st.subheader("真实实验结果")
    choices = [name for name in ("main", "ablation", "smoke") if (ROOT / "results" / name / "summary.json").exists()]
    if not choices:
        st.info("尚无已生成的 summary.json。全量实验结束后，此页面直接读取实际统计，不显示预设指标。")
        return
    selected = st.selectbox("实验结果目录", choices)
    path = ROOT / "results" / selected / "summary.json"
    summary = read_json(path, {})
    st.caption(f"来源：results/{selected}/summary.json。重复种子不能视为新增独立样本。")
    rows = metric_rows(summary)
    if rows:
        frame = pd.json_normalize(rows)
        principal=['mode','attack_runs','normal_runs','asr','direct_asr','indirect_asr','canary_leak_rate','normal_completion_rate','attacked_safe_completion_rate']
        display=frame[[c for c in principal if c in frame]].rename(columns={'mode':'配置','attack_runs':'攻击运行','normal_runs':'正常运行','asr':'主ASR','direct_asr':'直接ASR','indirect_asr':'间接ASR','canary_leak_rate':'Canary泄露率','normal_completion_rate':'正常完成率','attacked_safe_completion_rate':'受攻击安全完成率'})
        st.dataframe(display, use_container_width=True, hide_index=True)
        numeric = [name for name in ("asr", "attack_success_rate", "canary_leak_rate", "normal_completion_rate", "safe_completion_rate", "normal_task_completion_rate") if name in frame]
        if numeric and "mode" in frame:
            st.bar_chart(frame.set_index("mode")[numeric], horizontal=False,stack=False,y_label='比例（0至1）')
    with st.expander("完整统计与分母", expanded=not bool(rows)):
        st.json(summary)
    st.download_button("下载指标 JSON", data=json.dumps(summary, ensure_ascii=False, indent=2), file_name=f"{selected}_summary.json", mime="application/json")
    st.caption("主 ASR 保留预设攻击运行作为分母。接触率、解析失败、超时、耗尽与 pending 必须结合阅读；不能把模型不会调用工具解释成防御收益。")


st.markdown('<div class="hero-kicker">LOCAL AGENT SECURITY LAB</div>', unsafe_allow_html=True)
st.title("本地小模型 Agent 间接提示注入攻防与污点追踪系统")
st.markdown('<div class="boundary">本机模型推理 · 全部业务数据与操作均为模拟 · 确定性网关执行安全决策</div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("实验控制台")
    views=["单案运行", "真实记录回放", "实验指标"]
    requested_view={'live':0,'replay':1,'metrics':2}.get(st.query_params.get('view','live'),0)
    view = st.radio("工作模式", views,index=requested_view)
    st.divider()
    dataset_label = st.selectbox("数据集", ["开发集", "正式测试集"],index=1 if st.query_params.get('dataset')=='test' else 0)
    dataset_path = ROOT / "data" / ("dev.jsonl" if dataset_label == "开发集" else "test.jsonl")
    try:
        cases = read_cases(dataset_path)
    except (OSError, ValueError) as exc:
        cases = []
        st.error(f"数据集读取失败：{type(exc).__name__}")
    kinds = ["全部", "normal", "attack"]
    kind = st.selectbox("任务类型", kinds)
    filtered = [case for case in cases if kind == "全部" or case.get("kind") == kind]
    case_index=next((i for i,c in enumerate(filtered) if c['id']==st.query_params.get('case')),0)
    case = st.selectbox("选择案例", filtered,index=case_index, format_func=lambda item: f"{item.get('id')} · {item['runtime'].get('task', '')[:36]}") if filtered else None
    mode = st.selectbox("防御配置", list(MODES), index=list(MODES).index(st.query_params.get('mode','taint_policy')) if st.query_params.get('mode','taint_policy') in MODES else 2, format_func=lambda value: MODES[value])
    seed = int(st.number_input("固定采样种子", value=11, min_value=0, max_value=2147483647, step=1))
    if view == "单案运行":
        start = st.button("运行本地模型案例", type="primary", use_container_width=True, disabled=case is None)
        if start and case:
            try:
                from taintlab.agent.runtime import run_case
                canary = "SIM_CANARY_" + secrets.token_hex(16)
                with st.spinner("本地模型正在提出动作，网关逐项校验…"):
                    record = run_case(copy.deepcopy(case["runtime"]), mode, seed=seed, canary=canary, confirmation_mode="pending")
                    record["case_id"] = case["id"]
                    try:
                        from taintlab.evaluation.evaluator import evaluate
                        record["assessment"] = evaluate(case, record, canary)
                    except (ImportError, KeyError, TypeError, ValueError):
                        pass
                    st.session_state["live_record"] = record
                    st.session_state["live_case"] = case
                    st.session_state["live_canary"] = canary
                    save_record(ROOT, record)
            except Exception as exc:
                st.error(f"运行未完成：{type(exc).__name__}。请检查模型服务和本地日志。")
    st.divider()
    st.caption("Qwen3-0.6B · 官方 GGUF Q8_0\n\n每任务最多 6 次工具调用。界面不会将模型提供的路径写入宿主文件系统。")

display_config()

if view == "实验指标":
    show_metrics()
elif view == "真实记录回放":
    files = history_files(ROOT)
    if not files:
        st.info("尚无真实运行记录。完成单案例或批量实验后可在此回放。")
    else:
        requested=st.query_params.get('record','')
        selected_index=next((i for i,p in enumerate(files) if p.stem==requested),0)
        chosen = st.selectbox("选择历史运行", files,index=selected_index, format_func=record_title)
        record = read_json(chosen, {})
        show_overview(record, replay=True)
        timeline, graph, state, confirmation = st.tabs(["动作时间线", "来源与污点图", "模拟世界状态", "确认审计"])
        with timeline:
            show_timeline(record)
        with graph:
            show_sources(record)
        with state:
            show_state(record)
        with confirmation:
            show_confirmation(record, replay=True)
else:
    record = st.session_state.get("live_record")
    show_overview(record)
    source, timeline, graph, state, confirmation = st.tabs(["任务与外部内容", "动作时间线", "来源与污点图", "模拟世界状态", "人工确认"])
    with source:
        show_case(st.session_state.get("live_case", case) if record else case)
    with timeline:
        if record:
            show_timeline(record)
    with graph:
        if record:
            show_sources(record)
    with state:
        if record:
            show_state(record)
    with confirmation:
        if record:
            show_confirmation(record, replay=False)

st.divider()
st.caption("范围：本地模拟知识库助理。保守来源依赖不等于模型内部精确因果，也不覆盖全部侧信道或自然语言事实污染。")
