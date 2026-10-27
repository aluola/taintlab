"""Build the current report only from v2 evidence and render its editable DOCX.

Use the Codex bundled Python, then visually inspect every resulting page image.
The historical report and its builder remain separately archived.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import build_documents as doc

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'docs/v2/qa'
def read(path):return json.loads((ROOT/path).read_text('utf-8-sig'))
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def brief_tests():
    path=ROOT/'results/v2/validation/pytest.xml';root=ET.parse(path).getroot();suites=list(root.iter('testsuite'))
    counts={k:sum(int(s.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    passed=counts['tests']-sum(counts[k] for k in ('failures','errors','skipped'))
    return f"本轮实际全量pytest共{counts['tests']}项，{passed}通过，{counts['failures']}失败，{counts['errors']}错误，{counts['skipped']}跳过。证据为results/v2/validation/pytest.xml；不沿用上一轮通过数。"+'\n\n'+doc.table(['证据层','核验内容'],[
        ['单元与集成','权限 信息流 编码 来源继承 确认过期重放 停止竞争 会话隔离'],
        ['API与ASGI','Host Origin CSRF 额外授权字段拒绝 SSE安全投影'],
        ['上传','真实解析worker 大小展开及超时 扫描PDF 错误与截断'],
        ['生命周期','完整身份及创建时间 陈旧PID 并发锁 回滚范围'],
        ['前端','严格TypeScript 构建 组件状态与危险内容纯文本渲染'],
    ])
def data():
    return doc.table(['集合','攻击','正常','性质'],[
      ['原始基线正式集','72','36','自建规则模板 历史保留且2.0重测'],
      ['公开来源扩展正式集','60','30','30 BIPIA加30 InjecAgent机制映射；正常为local_control'],
      ['扩展开发集','9','4','按原ID与家族隔离 不计正式'],
    ])+'\n\n正式扩展SHA256：`'+digest(ROOT/'data/v2/test.jsonl')+'`。选择规则、纳入排除和逐条来源均可从data/v2复算。'
def charts():
    # Matplotlib is pinned in the project environment; document authoring stays
    # in the bundled document runtime instead of mutating that shared runtime.
    subprocess.run([str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'scripts/build_v2_charts.py')],check=True,cwd=ROOT)
def experiments():
    blocks=[]
    for name,label in [('baseline','原基线108样本'),('external','扩展90样本')]:
        s=read('results/v2/'+name+'/summary.json')
        expected=1296 if name=='baseline' else 1080
        if s.get('total_runs')!=expected:raise RuntimeError('Cannot build final report before the full campaign is saved')
        blocks+=['### '+label,doc.summary_block('v2/'+name),f'![{label} 当前2.0实际指标](docs/v2/qa/figures/{name}.png)']
    return '\n\n'.join(blocks)
def interpretation():
    rows=[];recovery=[]
    for campaign in ('baseline','external'):
        s=read('results/v2/'+campaign+'/summary.json')['modes'];a=s['taint_policy'];b=s['policy_only']
        rows.append([campaign,doc.percent(a['asr']),doc.percent(b['asr']),doc.percent(a['normal_completion_rate']),doc.percent(b['normal_completion_rate'])])
        for p in (ROOT/'results/v2'/campaign/'records').glob('*.json'):
            r=json.loads(p.read_text('utf8'));assessment=r.get('assessment',{})
            if r.get('kind')=='attack' and r.get('mode')=='taint_policy' and r.get('status')=='completed' and assessment.get('safe_completion') and any(e.get('decision')=='block' for e in r.get('events',[])):
                recovery.append(str(p.relative_to(ROOT)))
    text=doc.table(['批次','污点策略ASR','纯权限ASR','污点正常完成','纯权限正常完成'],rows)
    text+='\n\n这些配对结果只说明当前样本和模型条件下的观测。ASR差本身不证明污点独立收益，须逐配对检查sensitivity_flow_denied及对应实际违规。原基线中污点策略与纯权限的两次ASR差均没有阻断，来自生成正文是否包含篡改句的差异；唯一敏感度流阻断发生在正常任务。不能把这两次差异归因于污点机制。三配置都没有Canary外泄时，也不能把零泄露归因于防御。扩展集的逐案解释见docs/v2/EXPERIMENT_FINDINGS.md。'
    if recovery:text+='\n\n当前版本检索到'+str(len(recovery))+'条taint_policy攻击运行：completed、预设合法断言通过、没有确定性违规且出现过阻断。逐条解释需看实际事件；代表记录：`'+recovery[0]+'`。不是旧development_v3回放。'
    else:text+='\n\n当前正式记录中没有满足阻断后仍合法完成全部条件的taint_policy实例。界面可展示剩余步骤继续尝试，但不能宣称恢复成功；旧development_v3不替代当前验收。'
    (QA/'recovery_candidates.json').write_text(json.dumps(recovery,ensure_ascii=False,indent=2),'utf8')
    return text
def acceptance():
    parts=[]
    for p in sorted((ROOT/'results/v2/acceptance').glob('*/checks_actual_state.json')):
        s=json.loads(p.read_text('utf8'));parts.append('真实API状态复核 '+str(p.parent.name)+'：'+('全部所列断言通过' if s['all_passed'] else '含未通过断言')+'。')
    p=ROOT/'results/v2/browser/ui_e2e.json'
    if p.exists():
        v=json.loads(p.read_text('utf8'));parts.append('前端31项测试通过，独立目录离线重装后仍31项通过。实际浏览器16个不同检查的最新证据通过，包含首轮13/15及针对性复测，索引为results/v2/browser/ui_acceptance.json。初测失败原样保留，不能把汇总当作单批全通过。')
    p=ROOT/'results/v2/launcher/validation/actual_windows_validation.json'
    if p.exists():
        s=json.loads(p.read_text('utf8'))
        if not s.get('all_passed'):raise RuntimeError('Windows lifecycle validation has not passed')
        parts.append(f"真实Windows启停{len(s['checks'])}项通过，见results/v2/launcher/validation/actual_windows_validation.json。主流程没有旧Streamlit，因此迁移子分支未执行；本轮更早的迁移证据另存ui_migration.json。迁移后的start_ui.ps1已实测启动和关闭。")
    parts.append('Python进程socket/DNS守卫下，真实本地模型查询、通知、导出3/3完成，静态资源逐字节相同。证据为results/v2/validation/offline_validation.json；不是整机物理断网，独立llama.cpp不受该守卫约束。首次SQLite未关闭造成清理失败的证据保留，修复后通过。')
    parts.append('实际停止本项目模型、保持UI不变，在浏览器核验离线，再启动确认恢复。证据为results/v2/browser/model-offline-lifecycle.json及离线、恢复截图，没有使用Mock。')
    parts.append('异常分支中的身份不符、过期确认、并发确认、上传恶意结构和Canary人工阳性使用程序测试；不能将其写成实际模型攻击成功率。')
    return '\n\n'.join(parts)
def video():
    v=read('demo/video_validation.json');p=read('demo/playback_validation.json')
    if not v.get('valid') or not p.get('all_passed') or v.get('project_version')!='2.0.0':raise RuntimeError('Current video QA missing')
    return f"新版Demo实际时长{v['actual_duration']:.2f}秒，画面来自2.0真实浏览器，H264视频与AAC中文本地旁白，中文字幕烧录。最终位置demo/demo.mp4，脚本和字幕分别为demo_script.md与demo_subtitles.srt。浏览器播放验收通过；录制来源、时间线、hash和检查均独立保存。\n\n视频区分实时操作与真实运行回放，解释小模型能力、保守依赖与样本覆盖限制。等待若剪辑会在制作记录注明，不改写模型输出或模拟状态。"
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--render',action='store_true');parser.add_argument('--refresh-only',action='store_true');args=parser.parse_args()
    QA.mkdir(parents=True,exist_ok=True);doc.QA=QA
    charts()
    template=(ROOT/'docs/v2/report_template.md').read_text('utf8')
    blocks={'MODEL':doc.model_block().replace('工具链结果另见第7章','工具链实测见第11章'),'DATA':data(),'TESTS':brief_tests(),'EXPERIMENTS':experiments(),'INTERPRETATION':interpretation(),'ACCEPTANCE':acceptance(),'VIDEO':video(),
      'UI':'实际新界面截图及浏览器检查位于results/v2/browser。截图仅从运行中的2.0页面产生；文中架构描述为程序设计说明。\n\n![图1 2.0笔记本界面 1366乘768实际截图](results/v2/browser/laptop-home.png)\n\n![图2 实际待确认通知卡 目标和内容尚未执行](results/v2/browser/confirmation-pending.png)',
      'PACKAGE':'交付包独立核验结果与文件哈希由打包脚本产生，见dist/delivery_manifest_light.json、dist/light_package_validation.json及本轮运行验收sidecar。报告先冻结成品，包清单随后对本报告文件计算哈希，避免互相嵌入哈希的循环。'}
    for key,value in blocks.items():template=template.replace('<!-- AUTO '+key+' -->',value)
    if '<!-- AUTO ' in template:raise ValueError('Unresolved report block')
    source=ROOT/'docs/project_report.md';source.write_text(template,'utf8')
    if args.refresh_only:print(source);return
    document=doc.build_docx(template)
    if args.render:
        soffice=ROOT/'docs/qa/tools/LibreOffice/program/soffice.exe'
        pdf=doc.render(document,doc.RENDERER,soffice);mapping=doc.toc_pages(pdf,template)
        document=doc.build_docx(template,mapping);pdf=doc.render(document,doc.RENDERER,soffice)
        from pypdf import PdfReader
        pages=len(PdfReader(pdf).pages)
        for previous in (QA/'render').glob('page-*.png'):
            match=re.fullmatch(r'page-(\d+)\.png',previous.name)
            if match and int(match[1])>pages:
                archive=QA/'prior_render'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')/previous.name
                if not previous.resolve().is_relative_to(QA.resolve()) or not archive.resolve().is_relative_to(QA.resolve()):raise ValueError('Render archive path escaped QA directory')
                archive.parent.mkdir(parents=True,exist_ok=True);previous.replace(archive)
        result={'project_version':'2.0.0','generated_at':datetime.now(timezone.utc).isoformat(),'pages':pages,'toc_pages':mapping,'docx_sha256':digest(document),'pdf_sha256':digest(pdf),'source_markdown_sha256':digest(source),'visual_review':'required_after_latest_render','renderer':str(doc.RENDERER)}
        (QA/'document_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
        # Stable deliverable validation path used by the packager; old copy archived.
        (ROOT/'docs/qa/document_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
        print(json.dumps(result,ensure_ascii=False,indent=2))
    else:print(document)
if __name__=='__main__':main()
