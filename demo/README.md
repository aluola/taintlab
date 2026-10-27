# 六项核心功能实际演示

当前交付为发行 **v2.0.1**、冻结运行时 **2.0.0** 的 [demo.mp4](demo.mp4)，编码实测 **270.000秒**。中文旁白由本机 Microsoft Huihui Desktop 离线合成，字幕见 [SRT](demo_subtitles.srt)，镜头稿见 [demo_script.md](demo_script.md)。业务全部模拟，没有真实邮件或业务数据库。

| 时间 | 内容 | 素材性质 |
|---|---|---|
| 00:00–00:10 | 模型与边界 | 当前生产界面实际录制 |
| 00:10–00:55 | F01 四工具及攻击动作 | 本轮实际本地模型运行、确认和下载 |
| 00:55–01:30 | F02 上传、读取、来源传播 | 本轮实际上传和读取 |
| 01:30–02:15 | F03 信息流拒绝与可用性代价 | 正常任务02e896c7…的当前版本真实回放 |
| 02:15–02:55 | F04 确认、拒绝、授权与越权 | 同一通知复看、独立拒绝、直接注入回放 |
| 02:55–03:40 | F05 四种模板生成及运行 | 规则预览与真实模型调用分开标识 |
| 03:40–04:20 | F06 检测器与真实指标 | 真实状态、原生控制台合成自检、正式汇总 |
| 04:20–04:30 | 交付与限制 | 同一首页录制片段作为结束页 |

画面来自实际浏览器或原生控制台录屏，没有改写DOM、注入伪造结果或伪造模型思维。等待被剪辑，各段原速度播放，没有延长静止帧；控制台裁去空白并等比缩放。完整区间、原素材SHA、操作/结果证据及重复片段说明见[剪辑清单](core_features/edit_decisions.json)。原take、音轨和中间成片本机保留，轻量包不包含这些大文件；公开manifest与SHA用于本机原证据核验。

F03是真实正常失败：secret上下文触发sensitivity_flow_denied，通知和导出为空。F04的recipient_not_granted是不同的白名单机制。F05直接与分段合法断言失败；分段仅读第一来源，间接通知复制了伪授权文字。F06合成阳性不是模型外泄，3层编码超出当前范围；当前扩展集C和policy_only均34/180，不证明独立污点收益，零Canary泄露不能因果归于防御。

旧240秒v2.0.0媒体作为本机历史档案；本轮不改写旧GitHub Release。当前根目录recording_timing、final_recording_metadata、selected_evidence、video_validation与playback_validation已绑定新core_features文件，旧v2视觉记录不证明本轮通过。

## 复现录制与制作

启动当前应用，使用本地依赖和模型。以下命令用于本轮素材制作；新录制会产生新的运行ID、doc_id和Canary，不保证逐字节复现旧模型答案。

```powershell
node scripts/capture_core_features.cjs --only=home,flow,unauthorized,results
node scripts/capture_core_features.cjs --allow-model --only=read,query,notification,export,upload,reject,direct,indirect,encoding,segmented
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/record_canary_console.ps1
```

录制器禁止外部网络请求，只操作生产页面。首次定位器超时和终端黑屏捕获失败保留在本机take；修复录制脚本不改变模型状态。公开安全投影不包含owner、cookie、下载凭据或活跃会话数据库。最终图件另通过确定性的裁切、箭头和编号生成，原像素保留。

本机有原take时可复算以下步骤。重新录制后须先更新prepare_core_video.py中的TAKES映射，以及compose_core_demo.py中的实际区间和记录清单，并实际查看视频帧再冻结EDL；不要盲用旧秒数。source_inventory明确原始素材只在本机、不随轻量包提供。

```powershell
.venv/Scripts/python.exe scripts/prepare_core_video.py
.venv/Scripts/python.exe scripts/compose_core_demo.py
.venv/Scripts/python.exe scripts/prepare_core_narration.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/synthesize_demo_voice.ps1 -Narration demo/narration.json -OutputDirectory demo/voice/core_features -Duration 270
.venv/Scripts/python.exe scripts/encode_demo.py demo/core_features/composed.mp4 --timing demo/core_features/recording_timing.json --voice demo/voice/core_features/voice.wav --subtitles demo/demo_subtitles.srt --output demo/demo.mp4 --qa-dir demo/core_features/qa --project-version 2.0.0
.venv/Scripts/python.exe scripts/finalize_core_media.py
$env:TAINTLAB_PROJECT_VERSION='2.0.0'
node scripts/verify_video_playback.cjs
```

[编码验证](video_validation.json)检查全片解码、黑屏、H264/AAC、1600×900、270秒、音轨非静音，以及37段字幕与离线语音文本/时间一致。[浏览器播放验证](playback_validation.json)覆盖各核心操作、结果与268秒结尾。[视觉审核](core_features/visual_review.json)逐帧记录AI观察范围，不把技术检查或静音浏览器测试冒称人工全片听审。

对应[核心指南](../docs/CORE_FEATURES_GUIDE.md)和[证据矩阵](../docs/FEATURE_EVIDENCE_MATRIX.md)提供步骤、原图与真实记录。当前正式2376条、历史1296条独立保留；本轮自由对话、交互攻击和合成检测器自检均不加入正式ASR。
最终成片校验：12,478,629字节；SHA256 `b164feb7d3f5816e3de76aba927513c5e4102dcf665d16a06ba2d5d2c37e3e61`。实际浏览器32点播放通过（末次268秒，累计4334帧中2帧掉帧，无媒体错误）；AI原尺寸抽查36帧，F03/F04/F06另有18帧独立复核，具体观察和修订记录见视觉审核JSON。
