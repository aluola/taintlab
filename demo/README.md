# 2.0 实际对话界面演示与制作

当前成片为demo.mp4，目标240秒，1600×900，H.264/yuv420p视频、AAC本地中文旁白和烧录中文字幕。实际编码及播放结果以video_validation.json、playback_validation.json和v2/qa/visual_review.json为准。旧Streamlit版本已独立归档，不作为当前能力证明。

## 内容与真实来源

| 时间 | 画面来源与讲解 |
| --- | --- |
| 0–20秒 | 当前React界面与本机Qwen3-0.6B配置 |
| 20–60秒 | 实时模型读取并提出通知，浏览器真实确认卡点击，实际模拟收件箱 |
| 60–85秒 | 实际上传、授权读取和来源标签 |
| 85–106秒 | 当前冻结直接注入同样本seed11的none与input_filter真实回放 |
| 106–120秒 | 另一个当前间接注入：真实网页中的2099伪造结论及被污染通知，回放补录 |
| 120–155秒 | 回到直接注入C记录：白名单阻断、来源图、Canary及合法内容失败 |
| 155–200秒 | 四类真实规则模板生成预览；预览本身不计攻击运行 |
| 200–212秒 | 当前原基线1296条记录的实际指标 |
| 212–240秒 | 当前扩展1080条记录、消融、开销和限制，实际页面补录 |

所有业务操作模拟。正式回放来自results/v2/baseline；两条实时操作另存results/v2/demo_live/records，不混入正式分母。逐条路径与哈希见selected_evidence.json。旧development_v3恢复记录没有用于新版Demo。

录制由scripts/record_v2_demo.cjs驱动真实浏览器，不注入DOM、不伪造模型回复或修改模拟状态。确认使用自动化点击真实卡片，明确作为测试辅助，不冒充成员人工工时。顶部持续标明实时/回放/预览和版本。

## 剪辑与质量边界

v2/edit_decisions.json记录7段实际文件时间裁切；v2/composition_manifest.json给出原文件及合成文件SHA256。原take尾部有Playwright保持的重复帧，因此依据实际25fps帧边界复核，不能把单调时钟结束时间当文件时长。补录修复了折叠卡未露出注入正文、扩展旁白却仍显示基线表的问题。导航等待被剪除并明确标注，没有加速模型推理、延长静态帧或改写结果。

完整原take及补录只保留于本机demo/v2/raw，轻量包不含原WebM、中间MP4、WAV和重复QA帧。轻量包保留成片、字幕、旁白稿、制作脚本、录制清单、来源哈希和必要模型记录。video_validation.json检查时长、编码、分辨率、音轨非静音、字幕旁白匹配、帧差异及黑屏；playback_validation.json实际在隔离浏览器跳转六处并播放推进。视觉抽查单独记录，不把自动检测当作全文人工听审。

## 本机重新录制

先按根README准备模型并启动项目，确保已有真实记录。浏览器只允许本机127.0.0.1，使用独立测试profile。每次重录会产生新的真实结果和不同等待时间，必须新建编辑决策并复核字幕，不承诺像素或模型输出完全相同。先归档旧成片和清单。

```powershell
.venv/Scripts/python.exe scripts/prepare_video_tools.py
$demoNode = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
& $demoNode scripts/record_v2_demo.cjs --plan
& $demoNode scripts/record_v2_demo.cjs --selection results/v2/demo_selection.json
& $demoNode scripts/record_v2_demo.cjs --selection results/v2/demo_selection.json --pickup indirect
& $demoNode scripts/record_v2_demo.cjs --selection results/v2/demo_selection.json --pickup results
# 按新视频的真实时间与SHA更新edit_decisions.json之后执行
.venv/Scripts/python.exe scripts/compose_v2_demo.py demo/v2/edit_decisions.json
.venv/Scripts/python.exe scripts/prepare_v2_narration.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/synthesize_demo_voice.ps1 -Narration demo/narration.json -OutputDirectory demo/voice/v2 -Duration 240
.venv/Scripts/python.exe scripts/encode_demo.py demo/v2/intermediate/composed.mp4 --voice demo/voice/v2/voice.wav --qa-dir demo/v2/qa --project-version 2.0.0
$env:TAINTLAB_PROJECT_VERSION='2.0.0'
& $demoNode scripts/verify_video_playback.cjs
```

录制脚本可用TAINTLAB_PLAYWRIGHT指定Playwright包，TAINTLAB_CHROMIUM指定本地Chromium。播放验证用CODEX_RUNTIME_NODE_MODULES指定Playwright包。中文音轨来自Windows Microsoft Huihui Desktop/System.Speech，无云端TTS；叙述文字与实际模型输出严格分开。语音局部节奏调整有界并记录在voice_manifest.json，不调整视频或模型运行速度。

当前没有阻断后仍安全完成原任务的正式成功实例，没有证明污点的独立收益，各配置Canary都为零也不能归因防御。完整策略对事实污染仍会失败；原始记录、分母和失败没有因演示改写。成员信息及真实工时待补充。
