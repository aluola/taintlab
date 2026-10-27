# 公开分发白名单与历史审计

公开分发固定入口为 `.venv/Scripts/python.exe scripts/build_package.py --public`。使用步骤见[公开发布说明](README.md)；该入口在原工作区只验证原件并创建白名单暂存目录，在已有公开仓库中构建轻量 ZIP。脚本不初始化 Git、不提交、不创建远程、不推送。v2.0.1 必须从最新公开 `origin/main` 建立分支，经 PR squash merge 后打包；暂存目录用于文件比较与同步，不能再次创建独立公开历史。原本地仓库、历史、完整证据包与原始验收文件保持原样。

## Git 历史只读审计

`scripts/audit_publication.py` 遍历所有可达提交的树，记录所有 blob 的路径、大小和对象标识；同一 blob 的重命名路径也保留。每个唯一 blob 按字节扫描凭据模式、模拟 Canary、联系地址与本机路径。输出只包含路径、分类和计数，绝不包含匹配值、令牌哈希或原文片段。脚本不联网试验任何凭据。

v2.0.0 发布前的初次审计覆盖 5 个提交、302 个唯一 blob、244 个历史路径，共 3,828,411 字节。1 个初筛认证字段实际是 Cookie 名称常量，49 个初筛联系地址实际是 Playwright 录屏文件名；复核后无未解决的凭据候选。254 个 Canary 命中属于模拟/测试内容。73 处本机路径不是密钥；但旧诊断和制作环境资料不属于公开用户所需内容，因此当时采用独立白名单快照。后续更新沿用已建立的公开历史，不重复初始化。

这不是“任何秘密均不存在”的证明，也不宣称凭据在线验证。文本模式不能覆盖所有类型、编码和压缩媒体内的信息。公开摘要为 `results/publication/history_audit_public.json`；逐 blob 清单 `private_history_audit.json` 只保留在原工作区，不进入 Git 白名单或 Release。

## 必须真实跟踪的公开文件

- 项目自有后端、前端、测试、运行/制作脚本、依赖锁、配置、根目录启动/关闭 CMD 与 README；AGENTS仅保留项目维护段，私人通知规则和邮箱不得进入公开快照，投影差异记录在清单中。
- `frontend/dist` 的实际生产产物，前端输入/产物清单、npm lock；日常运行不依赖 npm 开发服务。
- 全部 3672 条正式原始记录：历史 main 972、ablation 324，当前 v2/baseline 1296、v2/external 1080；配对场景、配置 manifest、CSV/JSONL、汇总与冻结文件。正式原始字节不修改，不按成绩删选。
- 当前 Demo MP4、字幕、演示稿、必要回放来源和制作元数据；旧 development_v3 恢复来源仅以旧版本身份保留。
- 项目过程报告 PDF/DOCX/Markdown，`docs/USER_MANUAL.md/.docx/.pdf`，`docs/assets/user-manual` 的原图、标注图、配置与制作说明。
- 数据来源、固定版本、逐条映射、许可文本和冻结记录。来源适配不能称为官方基准完整复现。
- 当前手册 QA 的 JSON/Markdown。逐页 PNG、渲染日志与中间媒体不发布。手册captures目录只保留每轮capture_manifest.json，不保留重复PNG；清单内原take路径是本机制作证据引用，最终raw图片通过figure_index中的SHA映射核验。

文件被 `.gitignore` 忽略，不代表已上传。准备脚本输出精确 NUL 分隔 pathspec；维护者在已有公开分支中，用 `git --literal-pathspecs add -f --pathspec-from-file=<实际pathspec> --pathspec-file-nul` 跟踪已审查清单。禁止宽泛 `git add -f .`。随后运行 `scripts/prepare_publication.py --root <公开仓库> --check-tracked`，逐项核对索引跟踪和当前文件 SHA。远端 commit/tree 与 Release 下载验证另行完成，不能用本机文件存在冒充上传成功。

## 排除与公共摘要

任何层级的 web_private、凭据、cookie/owner/session/上传运行状态、SQLite、模型权重、vendor、虚拟环境、node_modules、PID/锁、日志、原始录屏和中间音视频均排除。参考仓库源码与未经明确授权再分发的第三方正文不得进入白名单。不会擅自给自有代码添加 MIT 或其他许可。

原机器环境、原始生命周期及详细安装/浏览器输出不直接公开。需要保留的验收角色生成明确标注 `publication_summary=true` 的公共摘要，含 `original_evidence_sha256` 和来源相对路径，保留必要检查、次数、产物哈希和结论；不复制机器身份、进程参数、认证信息与上传正文。这不是重新执行验收，也不修改原文件。浏览器索引内引用的摘要 SHA 按公开后的实际文件重新绑定。

播放、预检和安装结果分别汇入`results/publication/acceptance_summary.json`与`test_summary.json`。v2.0.0 的6点播放、11项Windows预检、4项浏览器检查及8项安装测试属于历史证据；本轮当前视频采用新的32点播放记录与新视频SHA，最终全套回归优先读取`results/core_features/validation/pytest_release.xml`。数量从真实文件读取，不由模板写死；安装、打包子集不叠加为额外独立测试。历史预检不冒充本轮重新安装或远端Release下载验收。

图片必须由实际项目界面采集或明确标注设计示意。手册图像清单与最终 QA 绑定文件哈希；不能使用私人聊天、凭据或第三方正文截图。

## 可审查快照与再打包

`PUBLICATION_MANIFEST.json` 记录来源 commit、逐文件来源/公开 SHA、字节数、转换类型、来源 Git 跟踪状态和排除原因。`configs/publication.json` 明确白名单暂存与现有公开历史的同步策略。新暂存目录必须不存在，避免覆盖；脚本不改变原 Git 历史。

v2.0.1 发布顺序固定为：提交原工作区本轮源文件后，运行 `prepare_publication.py --destination <新暂存目录>`；公开仓库 fetch 最新 `origin/main` 并从其建立本轮分支；生成并审查下面的三方同步计划，执行文件同步；精确 force-add、检查实际索引、提交、推送、创建 PR 并 squash merge。最后更新本机公开 main，在合并提交运行 `build_package.py --public`，由该提交创建新 tag/Release。不得覆盖 v2.0.0 或使用 `allow-unrelated-histories`。

```powershell
# 只读计划；target 是已有的干净公开分支，不是新 Git 仓库。
.venv/Scripts/python.exe scripts/prepare_publication.py --staging <暂存目录> --sync-target <公开仓库> --base-ref origin/main --baseline-ref v2.0.0 --sync-plan <本机计划.json>
# 仅在计划无冲突且输入未变时写入已批准的文件，不执行任何 Git 写操作。
.venv/Scripts/python.exe scripts/prepare_publication.py --apply-sync <本机计划.json>
```

三方比较以旧 Release 的 `PUBLICATION_MANIFEST` 为来源基线，将暂存内容与当前公开分支逐路径比较。仅原工作区变化时更新；仅公开分支变化时保留；双方变化且字节不同则拒绝同步。公开分支新增的允许发布文件保留，未知白名单角色或凭据模式需人工审查；脚本不推断删除，也不覆盖未提交修改。正式记录任何字节差异直接拒绝。计划绑定暂存清单 SHA、公开 HEAD、已获取 main 与逐文件 SHA，执行前复核；在独立临时目录验证拟合并结果后才写入目标。临时验证目录不创建 Git 仓库。

`PUBLICATION_MANIFEST.source_commit` 始终表示原工作区来源提交，并记录公开分支基线、保留远端修改与文件转换。包内 `DELIVERY_MANIFEST.git_commit` 则绑定打包时已合并的公开 main 提交。两种提交语义分开，不回写互相引用的 SHA；ZIP、交付清单和匿名下载验收留在 Git 源码清单之外。

本轮新增两份六章专题文档的 MD/PDF/DOCX、`FEATURE_EVIDENCE_MATRIX.md`、最终截图与配置、开发架构示意、模拟输入、核心功能精简记录、Canary 机制自检及性能公开摘要。原始性能 PID/JSONL、活跃会话、重复截图和录屏中间文件留在本机。`process_memory_public.jsonl` 仅删除 PID 字段，摘要绑定它和原始取证哈希；不把这些新采样加入正式实验分母。新版视频为六项功能操作演示，时长按实际 180–300 秒验收，运行核心仍为 2.0.0。

六章视频的 `demo/core_features/source_inventory.json` 与 `recording_timing.json` 属于必须公开的复现配置；原片路径明确为本机证据，不意味着原片随包发布。`composed.mp4`、中间音轨和原始录屏继续排除。旧 `demo/v2` 元数据保留历史角色，不能为当前六章视频提供验收结论。

公开快照默认运行 `scripts/build_package.py` 时，只从明确公开清单选文件。新出现的本地运行状态、私人诊断和缓存不会自动加入。正式记录、冻结数据、前端静态资源、视频及报告仍执行原有强校验；手册新增 MD/DOCX/PDF、页数、视觉结论与图像/配置哈希检查。独立解包另检查文档容器、中文内容、PDF 页数、媒体完整解码和全新环境安装。

公共摘要不增加正式实验分母，不将旧恢复视频当作当前成功，不把零 Canary 归因于防御，不声称已证实污点追踪的独立安全收益。成员姓名、学号、实际分工与真实工时仍待用户提供。
