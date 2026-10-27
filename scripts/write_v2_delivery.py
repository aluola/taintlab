"""Write the current delivery checklist from actual saved acceptance evidence."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads((ROOT/path).read_text('utf-8-sig'))
def main():
    test=ET.parse(ROOT/'results/v2/validation/pytest.xml').getroot().find('testsuite')
    video=read('demo/video_validation.json');play=read('demo/playback_validation.json');report=read('docs/qa/document_validation.json')
    integrity=read('results/v2/validation/experiment_integrity.json');windows=read('results/v2/launcher/validation/actual_windows_validation.json')
    assert integrity['all_passed'] and windows['all_passed'] and video['valid'] and play['all_passed']
    assert video['project_version']==report['project_version']=='2.0.0'
    lines=['# 2.0 当前交付与验收清单','',
      '当前版本2.0.0。历史v1清单保存在docs/history/DELIVERY_5c2a75c.md，历史完整包dist/taintlab_project.zip及旧1296条正式记录保留。以下仅按本轮实际证据填写，包字节数与SHA256由本轮独立清单生成。','',
      '## 已完成交付物','',
      '| 内容 | 实际位置及依据 |','| --- | --- |',
      '| React对话界面与FastAPI | frontend/src、frontend/dist、src/taintlab/web；同源8501 |',
      '| 六项能力与四个模拟工具 | src/taintlab；来源与权限来自后端，通知和文件只改模拟状态 |',
      '| 原始基线数据 | data/test.jsonl 72攻击36正常，字节未改 |',
      '| 公开来源扩展 | data/v2/test.jsonl 60攻击30本地正常；来源及许可逐条记录 |',
      '| 历史原始记录 | results/main 972及results/ablation 324，v1只读 |',
      '| 当前原始记录 | results/v2/baseline 1296及results/v2/external 1080，全部local_llama_cpp |',
      '| 当前独立复算 | results/v2/validation/experiment_integrity.json 50项检查全部通过 |',
      f"| 后端全套测试 | 本轮{test.get('tests')}项；失败{test.get('failures')}，错误{test.get('errors')}，跳过{test.get('skipped')}；pytest.xml |",
      '| 前端验证 | 31项单元测试；全新目录npm ci离线缓存构建与逐字节比对；frontend/qa |',
      '| 实际浏览器 | results/v2/browser；读取、查询、通知确认拒绝、下载、上传、停止、四模板和回放；初测失败与复测分别保留 |',
      '| Windows启停 | 根启动项目.cmd、关闭项目.cmd；18项真实检查，实际模型离线及恢复截图 |',
      f"| 当前Demo | demo/demo.mp4；{video['actual_duration']:.2f}秒H264/AAC，中文字幕与本地中文旁白，实际浏览器播放通过 |",
      f"| 当前项目报告 | docs/project_report.md、dist/project_report.docx、dist/project_report.pdf；{report['pages']}页，逐页渲染检查 |",
      '| 成员模板 | docs/members_workload.md与.csv；真实姓名学号贡献工时待补充 |','',
      '## 本轮补齐与验证边界','',
      '上传支持TXT、Markdown、文本PDF及DOCX，独立工作进程有大小、展开与时间限制；超出窗口有提示。真实API成功完成读取、查询、通知和导出；私有通知首测目标误选被阻断，补充所选目标ID后真实写入私有箱，失败证据保留。审计遮蔽在原始状态评测之后，因此原文状态与可见预览分别检查。','',
      '人工确认绑定run和动作哈希，由服务器查找pending；过期、并发、重复、篡改及停止竞争由程序测试覆盖。浏览器验收使用自动化点击真实确认卡，不虚构成人员工时。页面刷新、事件重连与重复请求不应重复通知；无原始模型token直接输出。','',
      '离线验证在Python进程阻止非回环socket/DNS，实际本地模型查询、通知、导出3/3完成，静态资源逐字节相符；不等于整机物理断网，独立llama.cpp进程不受该Python守卫约束。第一次SQLite清理失败保留，显式关闭连接后通过。新包的独立解压与全新venv验收由scripts/verify_light_package.py执行，结果在dist/light_package_validation.json；新解压真实模型验证另有sidecar，不复制旧venv。','',
      '## 当前版本实际指标','',
      '| 当前集合 | 配置 | ASR成功数与分母 | 正常完成数与分母 | 越权执行数 | Canary泄露数 |','| --- | --- | --- | --- | --- | --- |']
    for folder,title in [('baseline','原基线重测'),('external','公开来源适配')]:
        s=read('results/v2/'+folder+'/summary.json')
        for mode in ('none','input_filter','taint_policy','policy_only'):
            g=s['modes'][mode];a=g['attack_runs'];n=g['normal_runs']
            ratio=lambda key,den:f"{round(g[key]*den)}/{den}（{g[key]*100:.2f}%）"
            lines.append(f"| {title} | {mode} | {ratio('asr',a)} | {ratio('normal_completion_rate',n)} | {round(g['unauthorized_execution_rate']*a)} | {round(g['canary_leak_rate']*a)} |")
    lines += ['', '详细接触率、直接与间接、过滤误伤、状态、耗时、token、确认开销和逐配对解释见docs/v2/EXPERIMENT_FINDINGS.md、metrics.jsonl/CSV及summary.json。正常完成要求completed与真实状态断言同时满足；自由对话不自动评定。三个种子是配对重复，不增加独立样本数。','',
      '## 仍保留的研究和成员信息边界','',
      '- 当前2.0没有阻断后仍安全完成全部合法任务的实例，不能用旧development_v3替代。直接注入案例中确实继续发出了合法目标通知，但内容不满足断言，因此不记成功。',
      '- 本批未证明污点追踪相对纯权限的独立安全收益。原基线两次ASR差都没有block，扩展净差为零；来源追踪机制测试不能替代真实模型因果证据。',
      '- 各模式Canary均零，无防御同样为零；不能把零外泄归因防御。事实污染在当前完整策略中仍发生。',
      '- 公开来源机制映射不是BIPIA或InjecAgent官方完整复现；30正常任务明确是local_control。InjecAgent原攻击正文没有再分发。',
      '- 成员姓名、学号、实际分工和真实人工工时待补充；AI辅助、自动化浏览器和工具运行时间不能冒充个人独立劳动。',
      '- 上传不支持扫描PDF OCR，正文和历史有预算；依赖图不是内部精确因果或所有侧信道防护。非Windows平台未验证。','',
      '## 固定轻量交付流程','',
      '每轮先测试、构建前端、实测并冻结报告和视频，再默认运行scripts/build_package.py生成dist/taintlab_project_light.zip。自己的delivery_manifest_light.json和SHA256SUMS_light.txt说明版本、时间、包含/排除及逐文件哈希。新包不沿用旧包清单。最终ZIP哈希和解压验收作为sidecar，避免把包自身校验循环嵌入包内。','',
      '包含所有历史与当前3672条正式原始记录、必要演示记录、数据来源许可、源码、构建产物、依赖、脚本、报告和最终视频。排除模型权重、推理程序、venv、node_modules、会话数据库及凭据、PID、运行锁、大日志、重复渲染与音视频中间材料。完整证据包单独保留；旧轻量包在替换前自动备份。']
    (ROOT/'docs/DELIVERY.md').write_text('\n'.join(lines)+'\n','utf8')
    print('Current delivery checklist written from completed evidence.')
if __name__=='__main__':main()
