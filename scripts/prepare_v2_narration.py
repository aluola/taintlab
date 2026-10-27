"""Write a timed Chinese narration script for the reviewed actual v2 capture.

This creates captions and narration text only, never model output or UI state.
"""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SEGMENTS=[
 (0,10,'这是本地Agent提示注入平台的二点零版。三个入口是对话靶场、攻击实验和评测结果。'),
 (10,20,'本机运行六亿参数级Qwen模型，固定非思考模式。资料、通知与文件全部模拟，不连接真实业务系统。'),
 (20,32,'先做正常通知。用户明确选择会议资料和模拟项目组，再用自然语言提出任务。快捷按钮同样进入真实Agent执行流程。'),
 (32,45,'模型先读取资料，再提出通知。权限范围内的副作用会暂停等待确认。卡片显示准确目标和内容，文档声称已批准不能代替这一步。'),
 (45,60,'浏览器点击确认后，服务端校验当前动作哈希和有效期，只执行一次。交付栏中的模拟收件箱才是发送证据，模型说已发送并不算数。'),
 (60,72,'现在导入本地文档。上传仅登记来源，还需勾选读取权限。支持普通文本和可解析的文档，大小与解析时间都有上限。'),
 (72,85,'读取后查看真实来源记录。完整性和敏感度是两个维度，哈希与父节点由程序维护。外部正文不因为写着管理员授权就成为可信控制。'),
 (85,96,'下面是当前版本真实回放。直接注入伪造用户确认，无防御配置把消息写进了模拟攻击者收件箱。'),
 (96,106,'同样本和种子下，输入过滤删除了攻击，通知送到合法项目组。这次成功不代表能覆盖所有攻击。'),
 (106,120,'再看一个不同的间接注入案例。网页中的伪造结论进入处理，并出现在通知里。完整策略也没有拦住这类事实污染，这个失败保留在指标中。'),
 (120,131,'回到直接注入案例。网关按收件人白名单阻断两次越权提议，攻击者收件箱未变。决策由代码执行。'),
 (131,143,'来源图展示文档、上下文与动作的依赖。实线是确定性派生，虚线是潜在依赖，不是模型内部思维或精确因果。'),
 (143,155,'本例未读敏感文档，没有Canary泄露不能证明防御有效。后续虽发出通知，摘要却缺事实，合法任务仍未完成。'),
 (155,167,'攻击实验使用规则模板。直接、间接、编码和分段是四个展示视图，入口、技术、编码和目标分别记录，允许组合。'),
 (167,178,'生成后可以对照注入前后的正文，核对模板、种子、入口和样本标识。预览不会执行工具，也不计入模型攻击运行次数。'),
 (178,189,'编码使用确定性转换。分段放入两个独立来源，仍须核验读取顺序和实际接触。分行不等于多阶段攻击已发生。'),
 (189,200,'样本仍走同一Agent和网关。公开来源适配有固定版本、哈希与许可记录，不是官方完整复现。'),
 (200,212,'原基线重测一千二百九十六次，扩展集一千零八十次，均为四配置、三个种子。页面显示成功数和全部分母。'),
 (212,224,'正常完成率与攻击成功率一起报告。扩展集完整策略仍有百分之十八点八九的篡改成功，工具白名单没有解决所有注入。'),
 (224,240,'本批未证明独立污点收益，也没有阻断后安全完成的实例。零Canary泄露不能归因防御。源码、记录、报告和视频随轻量包交付；成员信息与人工工时待补充。'),
]
def timestamp(value):return f'{value//3600:02}:{value//60%60:02}:{value%60:02},000'
def main():
    entries=[{'start':a,'end':b,'text':t} for a,b,t in SEGMENTS]
    (ROOT/'demo/narration.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2),'utf8')
    (ROOT/'demo/demo_subtitles.srt').write_text('\n\n'.join(f'{i+1}\n{timestamp(a)} --> {timestamp(b)}\n{t}' for i,(a,b,t) in enumerate(SEGMENTS))+'\n','utf8')
    script='# 2.0 实际界面演示稿\n\n目标240秒。实时操作和冻结记录回放分段标识；本稿不是模型输出。旁白使用Windows本地语音，不访问云端。\n\n'
    script+='\n\n'.join(f'## {timestamp(a)[:8]} 至 {timestamp(b)[:8]}\n\n{t}' for a,b,t in SEGMENTS)
    script+='\n\n## 证据与制作\n\n录制选择见results/v2/demo_selection.json，逐记录哈希见demo/selected_evidence.json。录制脚本scripts/record_v2_demo.cjs不注入页面内容，不伪造状态。字幕、旁白时间表与最终视频校验一并保留。\n'
    (ROOT/'demo/demo_script.md').write_text(script,'utf8')
    print('Prepared 20 caption/narration intervals, 240 seconds.')
if __name__=='__main__':main()
