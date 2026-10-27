# TaintLab v2.0.0 首次公开发行

本地小模型Agent间接提示注入攻防与污点追踪教学平台。React/TypeScript生产界面由FastAPI同源提供，对话、四种模拟工具、来源/污点、确定性权限与真实确认、模板攻击及Canary评测全部本地执行。包含历史和当前共3672条正式模拟运行记录。

## 首次使用

下载taintlab_project_light.zip，核对SHA256SUMS后解压。安装64位Python3.12（实际验证3.12.10），在含两个中文CMD的根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
.\.venv\Scripts\python.exe .\scripts\model_prepare.py
.\启动项目.cmd
```

日常双击启动项目.cmd和关闭项目.cmd，界面http://127.0.0.1:8501/。普通运行不需Node/npm服务。参考仓库README及USER_MANUAL.pdf/docx。

当前验证Windows11、i7-13620H、16GB、RTX4050 Laptop6GB；不是最低配置声明，CPU/AMD/Linux/macOS未验证。默认下载Windows NVIDIA CUDA13.4 llama.cpp b11889，需兼容驱动。GGUF和两份推理ZIP固定下载合计1,227,700,721字节，不含Python依赖；首次联网下载并核验SHA，后续可离线使用。包内不附权重、推理程序、venv或node_modules。

## 附件

- taintlab_project_light.zip：可运行源码、前端生产文件、正式证据、手册、报告与视频。
- light_manifest.json：逐文件SHA256、来源版本、包含排除及ZIP哈希；SHA256SUMS为Release同级附件校验表。
- demo.mp4 / demo_subtitles.srt：240秒真实操作及明确标注回放，保留失败与研究边界。
- USER_MANUAL.pdf / USER_MANUAL.docx：真实截图标注的操作与实现手册，可编辑版同步。
- project_report.pdf / project_report.docx：项目过程与真实实验报告，与操作手册不同。
- PUBLICATION_ACCEPTANCE.json：发布前真实安装、启停、媒体及程序验证摘要。
- PUBLIC_DOWNLOAD_ACCEPTANCE.json：发布后才生成的匿名下载与独立运行验收；不回写已验证包。

下载后用Get-FileHash逐项对照SHA256SUMS。正式原始记录含合成Canary和模拟标识，不含真实凭据或活跃上传会话。项目自有代码尚未指定再分发许可证；Public不自动等于MIT。

## 结果适用范围

公开来源适配子集不是官方完整基准复现。扩展taint_policy ASR34/180，无防御31/180，尚不支持普遍降低攻击成功率；污点相对policy_only独立收益未证实。无防御也零Canary外泄，不能将零泄露归因防御。当前没有完整策略阻断后安全完成全部合法任务的成功实例；正常完成率含确认辅助，自动/辅助分列。全部业务模拟，属于教学研究平台；成员姓名、学号、实际分工和人工工时待补充。
