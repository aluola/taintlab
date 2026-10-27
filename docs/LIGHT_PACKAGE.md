# 轻量交付包与打包维护

打包器3.0.0默认生成轻量包，按文件职责保留源码、可运行前端、所有正式记录、数据来源与许可、最终报告及视频。不按攻击成绩、文件大小或是否成功选择正式样本。

## 命令及输出

在项目根目录运行：

```powershell
# 前端修改完成后：实际npm run build并记录源码/产物SHA；不生成ZIP
.venv/Scripts/python.exe scripts/build_package.py --prepare-frontend
# npm不在PATH时可增加 --npm "本机npm.cmd路径"

# 仅预览选择结果、体积、缺失项
.venv/Scripts/python.exe scripts/build_package.py --preview

# 所有正式评测、文档与视频验收完成后
.venv/Scripts/python.exe scripts/build_package.py

# 公开Git/Release固定入口：原工作区准备快照；快照提交/tag后再执行此命令打包
.venv/Scripts/python.exe scripts/build_package.py --public

# 仅在明确需要新完整证据归档时；已有同名完整包拒绝覆盖
.venv/Scripts/python.exe scripts/build_package.py --profile full
```

|配置|ZIP|独立清单|外部SHA清单|
|---|---|---|---|
|light|dist/taintlab_project_light.zip|dist/delivery_manifest_light.json|dist/SHA256SUMS_light.txt|
|full|dist/taintlab_project_full_v2.zip|dist/delivery_manifest_full_v2.json|dist/SHA256SUMS_full_v2.txt|

旧完整包taintlab_project.zip、delivery_manifest.json和SHA256SUMS.txt不再作为输出目标，保持原样。新版full若已存在则拒绝覆盖。新light构建之前，旧light ZIP、独立清单和SHA文件按实际ZIP哈希与微秒时间复制到dist/history/light/，核对源和备份哈希并保存回执；备份不嵌套进新包。预览不创建备份、不改任何归档。

ZIP顶层固定为taintlab_project/，含DELIVERY_MANIFEST.json及PACKAGE_SHA256SUMS.txt。外部清单记录最终ZIP大小和SHA；内部清单不递归宣称自身ZIP哈希。打包器只用Python标准库；无.git或Git可执行文件时元数据明确为空。

公开发布使用`--public`，规则见[公开分发白名单](publication/PUBLICATION_POLICY.md)。原工作区此命令只准备快照；维护者提交/tag后，在快照再次执行才打包。公开快照包含`PUBLICATION_MANIFEST.json`，在该快照中默认light只选清单文件，不会把后来产生的私人环境输出加入包。原工作区普通light仍是本地证据交付；不得直接把它当公开Release。公开准备不推送Git，不给未确定许可的自有代码添加MIT。

## 轻量纳入规则

- 根目录启动/关闭CMD、README、AGENTS、维护文件、Python配置及锁定依赖；src/全部Agent/安全/Web后端、scripts/、tests/、configs/及成员资料。
- frontend/src/、public/（若有）、dist/、scripts/、package.json、package-lock.json、Vite/TypeScript配置、index.html及build_manifest.json；frontend/qa中的clean_install_validation.json、clean_install_tests.json、unit_tests.json。日常运行使用编译后的dist，重建前端才需要Node/npm。
- v1的正式和开发集、冻结清单；data/v2/正式/开发JSONL、选择规则、逐条来源、许可文本、冻结与修正历史、生成测试。InjecAgent原文许可边界遵循docs/v2/DATA_SOURCES.md，不重新抓取未明确授权的正文进包。
- 旧main972条、ablation324条，新v2/baseline1296条、v2/external1080条，共3672条原始JSON。每组同时保留metrics.csv、metrics.jsonl、summary、experiment_manifest、paired_scenarios。新组未完成时打包失败，不能用部分记录冒充完成。
- configs/experiment_v2.lock.json、新旧模型/环境与关键验收、JUnit、当前v2独立完整性验收。旧运行时哈希仍是历史证据；当前源码另建清单。
- 最终dist/project_report.docx、PDF、docs/project_report.md，非QA正文、成员表，以及正文实际引用的图表和截图。引用的docs/qa图片也保留；不引用的逐页渲染图排除。
- `docs/USER_MANUAL.md/.docx/.pdf`、`docs/assets/user-manual/`原图/标注图/配置/说明，及`docs/publication/manual_qa/`的JSON和Markdown；手册逐页PNG、日志与临时文件排除。公开摘要仅允许明确命名的results/publication文件，私有历史扫描报告和临时Git pathspec不入包。
- 最终demo.mp4、字幕、演示稿、旁白文本、制作说明、选择证据、当前录制时序与视频/播放验证；demo/v2/的demo_upload.md、edit_decisions.json、composition_manifest.json、narration_synthesis.json、visual_review.json、recordings/*.json，以及当前v2/qa/subtitles.ass和final_frame_comparison.json。旁白合成清单以narration_synthesis.json为稳定入口，避免重复voice_manifest。旧demo/qa、旧voice清单、旧composition/patch/second_take元信息不进入轻量包，旧完整包保留历史。
- demo/selected_evidence.json当前引用的真实记录及相关开发campaign manifest/summary。当前结构为project_version、records数组、notes；records中的嵌套记录集合递归选择，每条path必须在允许的证据目录且sha256与实际文件匹配。results/v2/demo_live/records仅纳入明确引用的实时演示记录。未被引用的重复开发轨迹排除，开发和演示案例从不加入正式分母。
- results/v2/acceptance各次实际API验收的acceptance、checks、checks_actual_state摘要保留；原始API轨迹仅在demo明确引用时保留。浏览器验收的ui_e2e、ui_followup、layout_check、ui_acceptance及ui_visual_review保留；按ui_acceptance索引纳入它实际引用的带时间戳e2e/followup报告，核对已声明SHA。另保留model-offline/restored、model-offline-lifecycle、model-offline-visual-review、当前focused-source-graph-v2记录及video_timing/frame_alignment.json、timing_review.md。重复截图仍只按正文引用选择。
- docs/v2/qa的最终document_validation、structure_validation、visual_review_page_hashes、visual_review及分段逐页复核JSON保留，最终四个稳定验收入口与docs/qa逐字节核对。渲染PNG、重复PDF、中间日志不纳入；正文实际引用的v2指标图保留。
- 固定保留旧恢复包装results/demo/records/development_recovery.json、development_v3原始18f1f34fcc3ae112629d286a记录和版本manifest/summary，核对原始SHA及旧版本标识；不能作为当前冻结版恢复成功。
- results/launcher/validation/与results/v2/launcher/validation/中的JSON、Markdown、JUnit XML；其他launcher路径及截图不享有例外。

## 隐私及中间文件排除

两个profile都排除模型权重、推理/媒体工具二进制、虚拟环境、node_modules、缓存、秘密环境文件、PID、锁、tsbuildinfo、SQLite/数据库及WAL/SHM、现有ZIP、验证副本。frontend/.validation-build和.validation-target.txt也排除，原工作区中被策略阻止清理的暂存目录保持原样，不尝试绕过清理限制。任何层级的web_private/在遍历时即排除，包括owners、cookie、会话、checkpoint、确认状态及上传正文；被演示记录引用也不能绕过这一排除。

轻量包另排除日志、原片/补录、语音WAV及分段、逐页PNG、非正文QA截图、重复开发实验。新版轻量包不包含任何checkpoints.sqlite；已有逐任务记录和指标仍保留，恢复运行时由应用建立新的运行数据库。旧full归档内的历史SQLite不回写。

历史验收中保留的原片、截图路径和哈希是制作证据，不表示这些文件仍在轻量包中。重新制作视频需按Demo说明重新准备本地工具和录制素材。已合入最终MP4的音轨不以WAV重复打包。

## 源码、前端和静态资源一致性

--prepare-frontend真实运行npm run build；编译失败、期间源码变化或资源引用缺失，不会写成功清单。frontend/build_manifest.json记录实际返回码、源码和dist逐文件SHA、source_fingerprint和资源引用。运行前需要准备好npm依赖；脚本不自动联网安装依赖。

打包再次核对源码和dist的当前字节；源码修改但未重编译、缺chunk、HTML/CSS/JS缺引用、路径逃出dist、自动加载远端资源均失败。覆盖HTML资源属性、CSS url/@import、JS import/from及new URL(..., import.meta.url)。这是静态引用检查，不替代浏览器实际交互和断网验收。

每次清单的current_source.files及fingerprint记录当前交付Python、脚本、测试、配置、前端输入和启动入口。campaign_runtime_hashes单列四组历史/当前运行时哈希；文件哈希一致不等于重跑了模型实验。

## 最终打包门槛

|产物|实际验证要求|
|---|---|
|frontend/build_manifest.json|真实编译成功；当前源码/产物SHA一致；静态引用完整|
|frontend/qa/clean_install_validation.json及两个测试JSON|离线新目录安装通过；npm lock/产物SHA一致；实际Vitest报告零失败并与通过数匹配|
|results/v2/launcher/validation/actual_windows_validation.json|当前Windows实际生命周期验收文件保留，旧版同类验收分别保存|
|四组campaign|原始run ID、指标ID、计划数、summary数一致；backend_type为local_llama_cpp|
|v1/v2冻结清单|数据、来源索引、许可等文件SHA匹配|
|results/v2/validation/experiment_integrity.json|独立复算完成且all_passed=true|
|demo/video_validation.json|当前video_sha256、srt_sha256、valid；project_version匹配pyproject|
|demo/playback_validation.json|当前视频SHA、实际播放all_passed；project_version匹配|
|demo/v2/visual_review.json|当前video_sha256与明确通过结论；project_version匹配，旧版视觉复核不能满足此项|
|demo/v2制作证据|edit_decisions与composition哈希绑定；旁白对应当前narration；录制清单的selection/upload来源存在、被纳入且SHA匹配|
|results/v2/browser/ui_acceptance.json|当前版本与最新检查通过；索引引用的报告必须纳入、存在并匹配声明SHA；排除截图不代表图像重新复核|
|docs/qa/document_validation.json|DOCX/PDF/source_markdown_sha256正确，视觉复核完成；project_version匹配|
|docs/v2/qa最终四项稳定入口|与docs/qa的document_validation、structure_validation、visual_review_page_hashes、visual_review完全一致|
|docs/publication/manual_qa/manual_validation.json|版本、明确视觉通过、页数；当前USER_MANUAL三格式及声明图像/配置SHA匹配|
|demo/selected_evidence.json|项目版本匹配；递归检查records数组中每条path/sha256；所有引用存在且被纳入；空集合、缺哈希、陈旧哈希或Web私有路径均失败|
|旧recovery包装|原始记录SHA和development_v3标识保留|

这些证据必须来自实际工作，不能只补success字段。ZIP先写临时文件，CRC、条数和逐文件SHA通过后才替换light。文件在打包期间变化会失败，旧ZIP保持；备份仍可回查。不要在编译、正式评测、渲染或录制仍写入时构建最终包。

## 测试和独立解压验收

```powershell
.venv/Scripts/python.exe -m pytest tests/test_packaging.py tests/test_package_verification.py -q

# 最终ZIP生成后执行；不启动第二份模型/UI
.venv/Scripts/python.exe scripts/verify_light_package.py --install offline --run-packaging-tests
```

规则测试只在临时目录使用明确的合成文件，不充当模型、视频或报告实测。覆盖旧/新全部记录纳入、私有状态和数据库排除、源/产物变化、缺失/越界静态引用、冻结许可篡改、旧包备份、full不覆盖、源变化时保留旧包，以及解压路径/链接/大小/哈希保护。Demo记录数组和嵌套集合分别由打包器与独立解包器检查；覆盖实时记录纳入、未引用轨迹排除、声明哈希缺失/变更、目录越界及私有目录不能借引用进入包。v2制作、时序、浏览器索引报告和文档验收纳入有专门回归；当前视频变化、视觉检查不通过、录制输入变化、文档验收副本不同或浏览器报告丢失/变更，均不能继续声称打包验证成功。

独立验证在dist/package_light_verify/新建目录，核对逐文件清单、隐私排除、3672条正式索引、当前源码、前端输入和dist、冻结来源许可、README路径及可移植入口。可选用本机uv缓存建全新虚拟环境离线安装，不复制旧环境、不下载模型、不启动服务。媒体检查使用本地FFmpeg完整解码和文档解析，不声称重新人工逐页复核。

验证报告默认在ZIP外的dist/light_package_validation.json，绑定实际ZIP SHA，避免递归打包。最终答复必须使用本次light独立清单的路径、字节数、SHA、纳入与排除说明，不能借用旧包数字。

## 维护边界和历史事实

新必需产物应更新白名单、required_files与有效测试；正文图表应被Markdown实际引用。生命周期验收放validation子目录，活动状态另存；数据新版本保留来源/许可/冻结，新正式运行使用新campaign，不改历史验收。

旧完整包历史事实：最初轻量包改造时taintlab_project.zip为68,838,031字节，SHA256为9f04dd3d6eec16bdd09130f4822a2eb12f157baab7733f644a02b51ece5c71b3。该数值不是v2交付大小或新验收结论。首次模型/依赖准备按README执行；应用进程离线验收不等于整机物理断网。
