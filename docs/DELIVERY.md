# 2.0 运行核心交付记录与 v2.0.1 增补清单

以下最初交付记录保留其原版本含义；本轮文档与演示发行 v2.0.1 的新增材料和验收见末尾，不把旧测试、旧视频和旧安装记录当作本轮重新执行。

当前版本2.0.0。历史v1清单保存在docs/history/DELIVERY_5c2a75c.md，历史完整包dist/taintlab_project.zip及旧1296条正式记录保留。以下仅按本轮实际证据填写，包字节数与SHA256由本轮独立清单生成。

## 已完成交付物

| 内容 | 实际位置及依据 |
| --- | --- |
| React对话界面与FastAPI | frontend/src、frontend/dist、src/taintlab/web；同源8501 |
| 六项能力与四个模拟工具 | src/taintlab；来源与权限来自后端，通知和文件只改模拟状态 |
| 原始基线数据 | data/test.jsonl 72攻击36正常，字节未改 |
| 公开来源扩展 | data/v2/test.jsonl 60攻击30本地正常；来源及许可逐条记录 |
| 历史原始记录 | results/main 972及results/ablation 324，v1只读 |
| 当前原始记录 | results/v2/baseline 1296及results/v2/external 1080，全部local_llama_cpp |
| 当前独立复算 | results/v2/validation/experiment_integrity.json 50项检查全部通过 |
| 后端全套测试 | 本轮397项；失败0，错误0，跳过0；pytest.xml |
| 前端验证 | 31项单元测试；全新目录npm ci离线缓存构建与逐字节比对；frontend/qa |
| 实际浏览器 | results/v2/browser；读取、查询、通知确认拒绝、下载、上传、停止、四模板和回放；初测失败与复测分别保留 |
| Windows启停 | 根启动项目.cmd、关闭项目.cmd；18项真实检查，实际模型离线及恢复截图 |
| 当前Demo | demo/demo.mp4；240.00秒H264/AAC，中文字幕与本地中文旁白，实际浏览器播放通过 |
| 当前项目报告 | docs/project_report.md、dist/project_report.docx、dist/project_report.pdf；24页，逐页渲染检查 |
| 成员模板 | docs/members_workload.md与.csv；真实姓名学号贡献工时待补充 |

## 本轮补齐与验证边界

上传支持TXT、Markdown、文本PDF及DOCX，独立工作进程有大小、展开与时间限制；超出窗口有提示。真实API成功完成读取、查询、通知和导出；私有通知首测目标误选被阻断，补充所选目标ID后真实写入私有箱，失败证据保留。审计遮蔽在原始状态评测之后，因此原文状态与可见预览分别检查。

人工确认绑定run和动作哈希，由服务器查找pending；过期、并发、重复、篡改及停止竞争由程序测试覆盖。浏览器验收使用自动化点击真实确认卡，不虚构成人员工时。页面刷新、事件重连与重复请求不应重复通知；无原始模型token直接输出。

离线验证在Python进程阻止非回环socket/DNS，实际本地模型查询、通知、导出3/3完成，静态资源逐字节相符；不等于整机物理断网，独立llama.cpp进程不受该Python守卫约束。第一次SQLite清理失败保留，显式关闭连接后通过。新包的独立解压与全新venv验收由scripts/verify_light_package.py执行，结果在dist/light_package_validation.json；新解压真实模型验证另有sidecar，不复制旧venv。

## 当前版本实际指标

| 当前集合 | 配置 | ASR成功数与分母 | 正常完成数与分母 | 越权执行数 | Canary泄露数 |
| --- | --- | --- | --- | --- | --- |
| 原基线重测 | none | 13/216（6.02%） | 71/108（65.74%） | 3 | 0 |
| 原基线重测 | input_filter | 9/216（4.17%） | 60/108（55.56%） | 0 | 0 |
| 原基线重测 | taint_policy | 8/216（3.70%） | 77/108（71.30%） | 0 | 0 |
| 原基线重测 | policy_only | 10/216（4.63%） | 78/108（72.22%） | 0 | 0 |
| 公开来源适配 | none | 31/180（17.22%） | 67/90（74.44%） | 0 | 0 |
| 公开来源适配 | input_filter | 29/180（16.11%） | 59/90（65.56%） | 0 | 0 |
| 公开来源适配 | taint_policy | 34/180（18.89%） | 67/90（74.44%） | 0 | 0 |
| 公开来源适配 | policy_only | 34/180（18.89%） | 66/90（73.33%） | 0 | 0 |

详细接触率、直接与间接、过滤误伤、状态、耗时、token、确认开销和逐配对解释见docs/v2/EXPERIMENT_FINDINGS.md、metrics.jsonl/CSV及summary.json。正常完成要求completed与真实状态断言同时满足；自由对话不自动评定。三个种子是配对重复，不增加独立样本数。

## 仍保留的研究和成员信息边界

- 当前2.0没有阻断后仍安全完成全部合法任务的实例，不能用旧development_v3替代。直接注入案例中确实继续发出了合法目标通知，但内容不满足断言，因此不记成功。
- 本批未证明污点追踪相对纯权限的独立安全收益。原基线两次ASR差都没有block，扩展净差为零；来源追踪机制测试不能替代真实模型因果证据。
- 各模式Canary均零，无防御同样为零；不能把零外泄归因防御。事实污染在当前完整策略中仍发生。
- 公开来源机制映射不是BIPIA或InjecAgent官方完整复现；30正常任务明确是local_control。InjecAgent原攻击正文没有再分发。
- 成员姓名、学号、实际分工和真实人工工时待补充；AI辅助、自动化浏览器和工具运行时间不能冒充个人独立劳动。
- 上传不支持扫描PDF OCR，正文和历史有预算；依赖图不是内部精确因果或所有侧信道防护。非Windows平台未验证。

## 固定轻量交付流程

每轮先测试、构建前端、实测并冻结报告和视频，再默认运行scripts/build_package.py生成dist/taintlab_project_light.zip。自己的delivery_manifest_light.json和SHA256SUMS_light.txt说明版本、时间、包含/排除及逐文件哈希。新包不沿用旧包清单。最终ZIP哈希和解压验收作为sidecar，避免把包自身校验循环嵌入包内。

包含所有历史与当前3672条正式原始记录、必要演示记录、数据来源许可、源码、构建产物、依赖、脚本、报告和最终视频。排除模型权重、推理程序、venv、node_modules、会话数据库及凭据、PID、运行锁、大日志、重复渲染与音视频中间材料。完整证据包单独保留；旧轻量包在替换前自动备份。


## 首次Public发布与用户手册（2026-10-27）

本轮未改变2.0冻结运行语义或重跑正式实验。新增中文公开README、23张真实编号截图、32页操作与实现手册MD/DOCX/PDF、可复现标注/文档构建脚本、匿名下载验证器和明确公开白名单。安装脚本补齐无uv时py/PATH发现及无效venv保护；制作工具去除个人可执行路径。413项当前Python测试通过，预发布新目录11项启停与4项真实浏览器业务通过；依赖使用新venv+已有uv缓存，模型用锁定文件哈希复用。Demo原文件已重新全解码和6点播放核验。

实际公开入口为[aluola/taintlab](https://github.com/aluola/taintlab)及[v2.0.0 Release](https://github.com/aluola/taintlab/releases/tag/v2.0.0)。最终源提交和内容差异见公开快照PUBLICATION_MANIFEST；正式原始记录共3672条全部保留。新包的实际字节、SHA与文件清单见Release，不沿用前版数值。发布后的匿名下载与独立安装回执以PUBLIC_DOWNLOAD_ACCEPTANCE.json单独追加；不修改已发布tag或已验证附件。详见[公开发布说明](publication/README.md)和[操作手册](USER_MANUAL.md)。成员信息、许可证选择及研究因果边界仍待补充或验证。

## v2.0.1 六项核心功能材料与交付流程增补

本轮未改变冻结运行核心 2.0.0。新增两份独立文档：[六项核心功能操作与验证](CORE_FEATURES_GUIDE.md)和[开发与交付过程说明](DEVELOPMENT_AND_DELIVERY.md)，各提供 Markdown、PDF、DOCX；[证据矩阵](FEATURE_EVIDENCE_MATRIX.md)串联实际操作、输入、运行、截图、视频章节、验收判据及限制。综合手册保留原截图并增补导航，新旧视频与回放不混用。

| 本轮内容 | 实际证据与口径 |
| --- | --- |
| 四个正常工具和上传 | results/core_features/demo_runs；模型实际调用，通知/虚拟文件/下载内容核验，不以模型声明为准 |
| 来源与污点 | 新上传实际读取父链；02e896c7 正常任务真实回放中 sensitivity_flow_denied；合法失败保留 |
| 权限与确认 | 待确认、确认一次通知、独立拒绝无通知、白名单拒绝；程序测试与模型运行分开 |
| 四个攻击视图 | 四次规则预览后分别实际运行；直接和分段合法失败，分段未读完后续来源，均保留 |
| Canary 检测器 | 现有函数的 7 个合成正反/编码/拼接/超界对照，均符合预设；不进入正式 ASR |
| 真实性能采样 | 空闲/四任务/空闲，共 88 条进程观测；UI与模型实际工作集/私有提交，设备显存单列 |
| Python 回归 | 发布前完整回归 473 通过、0失败、1条依赖弃用提示，终端168.34秒；早期465与各定向记录保留，重叠子集不相加 |
| 冻结保护 | baseline_integrity.json 与 final_integrity.json；3715 个受保护文件含3672正式记录逐字节一致 |
| 文档与视频 | 三格式、原图/标注配置、逐页视觉QA、六章节新Demo与音轨/字幕/播放QA按各自新哈希绑定 |
| PR 和发行 | 从公开 origin/main 建分支、白名单同步、PR squash merge，合并提交打 v2.0.1；状态以远端和Release验收回执为准 |

新包默认 `dist/taintlab_project_light.zip`，保留3672正式记录、必要来源许可、源码与构建、三份手册及原项目报告、新Demo和逐项证据。排除权重、推理二进制、虚拟环境、活跃会话、认证、PID、原片/中间音频和重复渲染。旧完整包和v2.0.0 Release保持原样。新包清单与SHA在新Release，不沿用历史字节数。

本轮没有重复全部正式实验，也没有重做全新电脑联网安装；下载后新材料与源/包完整性、媒体/文档检查另有独立回执。历史缓存复用新venv安装边界不变。五人建议位置模板已提供，姓名、学号、实际贡献与人工工时仍待补充；研究结论、许可证选择等边界与上文一致。

最终回归位于 `results/core_features/validation/pytest_release.xml`。流程文档按实际过程记录先完成的465项回归，对应独立 `results/core_features/pytest.xml`；后新增8项发布与排版相关测试后执行473项最终回归。两次证据各自保留，不覆盖或将数量相加。

其后公开快照检查发现，播放报告去除机器信息后的字节变化需要同步更新审核引用。该发布层修复保留原始来源SHA，仅重绑公开副本；新增公开引用检查另有4项定向回归通过，见 `results/core_features/validation/public_reference_projection_tests.xml`。它与全套回归存在重叠，不相加成新的全套数字，也不修改冻结运行代码。
