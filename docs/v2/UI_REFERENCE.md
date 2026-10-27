# 对话界面参考调查与独立实现记录

记录日期：2026-10-27。当前实现位于 `frontend/`，日常由 Python 同源服务提供 `frontend/dist` 静态产物，不依赖 Vite 开发服务器、外部字体或 CDN。

## 实际调查的参考

按用户要求实际打开并检查了 [ChinaSiro/claude-code-sourcemap](https://github.com/ChinaSiro/claude-code-sourcemap) 的 README，以及消息列表、输入框、工具状态和权限组件。参考固定到 revision **`a8a678cb6244e6770e1e421767ff0987a1d95549`**；本机只读研究缓存为 `.cache/references/claude-code-sourcemap-a8a678cb`。通过 `git rev-parse HEAD` 复核该值。

该仓库 [README（固定 revision）](https://github.com/ChinaSiro/claude-code-sourcemap/blob/a8a678cb6244e6770e1e421767ff0987a1d95549/README.md) 明示它是从公开 npm 包 2.1.88 的 source map 还原的**非官方研究材料**，不是官方内部仓库结构；版权属于 Anthropic。检查对象主要是 React/Ink 终端界面，不是可直接移植的浏览器网页。

本项目仅借鉴普通交互组织方式：输入与消息分离、工具状态内嵌消息流、确认作为独立卡片、长日志按需展开。没有复制参考源代码、source map、React/Ink 组件、提示词、业务逻辑、样式、图标或包内资源；交付物不包含该参考仓库。新界面通过自己的 TypeScript API 契约、React DOM 组件与 CSS 实现，模型调用仍为本地 llama.cpp。

| 实际阅读路径（均在上述固定 revision） | 检查到的交互结构 | 本项目独立实现与边界 |
|---|---|---|
| [`restored-src/src/components/Messages.tsx`](https://github.com/ChinaSiro/claude-code-sourcemap/blob/a8a678cb6244e6770e1e421767ff0987a1d95549/restored-src/src/components/Messages.tsx) | 消息列表、折叠记录、确认队列与工具进行状态分别管理；列表可限制渲染范围并保持锚点 | `App.tsx` 按 run_id 合并后端安全投影；只在用户靠近底部时跟随滚动；历史默认收起。未移植其列表算法。 |
| [`restored-src/src/components/PromptInput/PromptInput.tsx`](https://github.com/ChinaSiro/claude-code-sourcemap/blob/a8a678cb6244e6770e1e421767ff0987a1d95549/restored-src/src/components/PromptInput/PromptInput.tsx) | 受控输入、onSubmit、粘贴/附件与选择状态分开处理 | `Composer.tsx` 使用原生 textarea；中文 IME 组合期间 Enter 不发送，Shift+Enter 换行。上传登记与任务提交是两个明确动作。 |
| [`restored-src/src/components/ToolUseLoader.tsx`](https://github.com/ChinaSiro/claude-code-sourcemap/blob/a8a678cb6244e6770e1e421767ff0987a1d95549/restored-src/src/components/ToolUseLoader.tsx) | 未完成、错误、完成状态有独立输入 | `ToolCard.tsx` 只使用服务器 allow/block/pending 等决策，不按计时器生成阶段或进度。状态“允许”不等同合法任务成功。 |
| [`restored-src/src/components/messages/AssistantToolUseMessage.tsx`](https://github.com/ChinaSiro/claude-code-sourcemap/blob/a8a678cb6244e6770e1e421767ff0987a1d95549/restored-src/src/components/messages/AssistantToolUseMessage.tsx) | 工具提议与已解决工具 ID 分开，输入先解析再显示 | 本项目不接收原始模型流；`ToolCard.tsx` 展示后端已经做可见性处理的参数和工具回执。 |
| [`restored-src/src/components/messages/UserToolResultMessage/UserToolResultMessage.tsx`](https://github.com/ChinaSiro/claude-code-sourcemap/blob/a8a678cb6244e6770e1e421767ff0987a1d95549/restored-src/src/components/messages/UserToolResultMessage/UserToolResultMessage.tsx) | 工具 ID 关联结果，区分取消、拒绝与错误 | `RunMessages` 与安全抽屉直接读取同一 Run 投影，拒绝不生成收件箱或文件；“已发送”自然语言不是执行依据。 |
| [`restored-src/src/components/permissions/PermissionRequest.tsx`](https://github.com/ChinaSiro/claude-code-sourcemap/blob/a8a678cb6244e6770e1e421767ff0987a1d95549/restored-src/src/components/permissions/PermissionRequest.tsx) | 权限请求组件与允许/拒绝回调分离 | `ConfirmationCard.tsx` 只显示后端 pending。提交字段仅 `request_id/action_hash/approve`，浏览器不能提交或修改 action、grant、checkpoint。 |
| [`restored-src/src/components/permissions/PermissionPrompt.tsx`](https://github.com/ChinaSiro/claude-code-sourcemap/blob/a8a678cb6244e6770e1e421767ff0987a1d95549/restored-src/src/components/permissions/PermissionPrompt.tsx)；[`PermissionDialog.tsx`](https://github.com/ChinaSiro/claude-code-sourcemap/blob/a8a678cb6244e6770e1e421767ff0987a1d95549/restored-src/src/components/permissions/PermissionDialog.tsx) | 确认选择与取消明确分支；标题、说明、正文分区 | 本项目确认卡同时展示工具、目标、内容、来源、哈希和过期时间；历史回放和失效确认不可执行，最终校验在服务端。 |

## 新界面的入口与组成

只有三个主导航：**对话靶场、攻击实验、评测结果**。历史会话默认折叠，审计信息放在右侧抽屉。消息正文保持简单，不把权限表、原始 JSON 和全量来源图常驻在对话中心。

- 对话靶场：居中的消息流、底部输入、读取文档/查询资料/发送通知/导出文件四个快捷入口、上传、真实运行停止和人工确认。快捷入口只填写任务并打开资源目录，均通过 `POST /api/sessions/{sid}/runs`。
- 任务参数：文档必须显式勾选，通知对象和虚拟导出目标取自服务端目录。关闭“敏感资料私有处理”时清除敏感源和私有目标；正文无法授予自己权限。
- 攻击实验：直接、间接、编码、分段四类预览；样本生成、注入前后来源和正式运行分开。运行只提交服务端保存的 preview_id。
- 安全抽屉：真实决策、实际 TaskGrant、来源图和节点、模拟交付、Canary 有界检测。授权先以易读字段展示工具、文档、目标、格式、额度、敏感度、确认、版本和有效期，再提供折叠 JSON。来源图按所选或最近动作的相关祖先聚焦，默认最多 14 个节点，可展开全部；折叠不改变底层来源。虚线代表潜在上下文依赖，不展示或伪造模型内部思维。
- 评测结果：从真实 summary/manifest 加载；优先选择当前 `v2_baseline`，当前和历史版本分开。三种主配置默认展示，policy_only 单独展开。主表同时显示比率与次数/分母，高级区域显示攻击接触、解析失败、超时、耗尽、pending、正常任务误拦原因、耗时、token、工具调用和确认事件。历史运行均标注“真实运行记录回放”，确认只读。

所有资料正文、模型最终内容、错误、名称、参数和预览使用 React 纯文本节点显示。没有 `dangerouslySetInnerHTML`、HTML Markdown 渲染器、远程 iframe、外部字体或资源。虚拟文件下载使用服务端签发的 download_id，模型提供的路径不作为宿主 URL。已构建产物只含项目 JS/CSS 与 index.html。

## 运行一致性与明确状态

1. `api.ts` 在 bootstrap 后持有 CSRF 值；POST 使用 `X-TaintLab-CSRF` 与同源 cookie。SSE URL 不放 CSRF 或身份 token。
2. 请求失败不自动重试副作用。相同内容的人工重试复用 request_id；服务端提供幂等保护。
3. SSE 按 session_id、sequence 合并；重复/过时事件不追加第二份运行。晚到的 HTTP 开始回执不能覆盖终态或更完整事件。
4. SSE 断线使用浏览器原生恢复机制；断线期间可只读轮询当前 Run，绝不重新提交运行。
5. 停止请求后显示“等待当前模型调用返回”。仅在服务器投影状态改变时显示已停止；既有副作用不会在界面消失。
6. `completed` 显示“运行结束”，同时保留独立任务评定。自由对话显示“未自动评定”，不能计入正式完成率。
7. backend_type 可见：`local_llama_cpp` 才显示“本地模型实测”；其他后端明确显示实际标识，不冒充真实模型。
8. 标签与 Canary 由后端安全投影提供。浏览器不自行去污，也不把 Canary 未发现解释成完整防泄露证明。

## 依赖、构建与验证

实际构建环境：Windows、Node.js 24.15.0、npm 11.12.1。直接依赖与开发依赖使用精确版本，完整传递依赖记录在 `frontend/package-lock.json`。本次使用 React/React DOM 19.3.1、TypeScript 7.0.2、Vite 8.3.5、Vitest 5.0.5。

首次准备与开发检查：

```powershell
Set-Location frontend
npm ci
npm test
npm run build
```

正常业务启动无需 npm、Vite、外网或 node_modules；Python 服务提供 `frontend/dist`。开发服务器只用于开发，若需要从 5173 调用严格同源 API，须通过受控本地代理配置；正式验收使用 API 自己提供的 8501 页面。

已实际通过最终 **31 项**前端单元/组件测试以及 TypeScript 严格检查、Vite 生产构建。测试明确使用 `scripted_ui_fixture` 合约夹具，覆盖正文 HTML 惰性显示、历史/过期/提交中确认、精确确认字段、私有选择撤销、IME、停止状态、跨会话和乱序事件、缺失指标不变零、次数/分母还原、聚焦图不丢失底层节点、当前结果优先、仅 download_id 构造下载路由与失败 mutation 不自动重试。机器报告为 `frontend/qa/unit_tests.json`。

还在全新临时目录以 `npm ci --offline --no-audit --no-fund` 从**已有准备缓存**安装 94 个依赖包，重新执行构建与 31 项测试，全部通过。该验证不等于全新电脑无需首次下载依赖。新目录产物与正式三份 dist 文件逐字节 SHA256 一致，证据为 `frontend/qa/clean_install_validation.json` 和 `frontend/qa/clean_install_tests.json`。验证缓存 `frontend/.validation-build/`、`frontend/.validation-target.txt` 与 `node_modules/` 已忽略，必须排除交付包。

这些单元测试不代表真实模型端到端结果。实际 API 联调、中文宽/窄屏截图与运行证据单独保存在 `results/v2/browser/`，不改写 v1 实验、视频或验收记录。

## 实际浏览器验收与保留的问题

使用真实同源 `taintlab-web 2.0.0` 服务和隔离的 Chromium 测试配置，阻止页面请求任何非 `127.0.0.1:8501` 资源。没有浏览器请求替身或伪造模型响应。截图尺寸包括桌面 1440×960、常见笔记本 1366×768、窄屏 390×844。

| 实际记录 | 结果与口径 |
|---|---|
| `ui_e2e_2026-10-26T17-12-36-626Z.json` | 首轮 15 项中 13 项通过：导航、响应式、文档提取、通知 pending 与刷新恢复/确认、拒绝无发送、真实导出下载、真实停止、四类生成预览和本地模型运行、只读历史回放。无 JavaScript 错误、无外部资源请求。 |
| 同一首轮的查询与上传 | 两项内容验收未通过：工具实际执行，但最终仅答“任务结果”。上传验收代码还错误猜测文档 ID 必须有 upload 前缀，已改为使用服务端实际登记 ID。初次失败保留，不包装成安全收益。 |
| `ui_followup_2026-10-26T17-19-00-715Z.json` | 两项针对性真实复验均通过。查询快捷填写更清楚的自然问题，模型返回 11月8日与11月3日；上传任务引用实际 doc_id，返回周四10:30与B202。没有硬编码答案或替换模型输出。 |
| `ui_followup_2026-10-26T17-33-09-419Z.json` | 易读授权、实际次数/分母、资源开销和来源图聚焦测试通过；14 个聚焦节点可展开为全部 25 个节点。 |
| `layout_check_initial_transition_capture.json` | 最初窄屏自动化点击遮罩中心时，被导航栏遮挡；截图也截到了 CSS 过渡中间态。改为点击可见遮罩区域、截图关闭过渡后，真实宽/窄屏检查通过。属于测试定位修复，没有修改业务状态。 |
| `ui_followup_2026-10-26T18-05-16-679Z.json` | 最终生产产物上重新执行导航、1366×768 与390×844三项实际浏览器检查，3/3通过，无 JavaScript 错误或外部资源请求。旧 `layout_check.json` 的初次失败仍保留。 |

最终证据入口为 `results/v2/browser/ui_acceptance.json`，逐项引用初始记录和复测，16个不同检查的最新证据均通过；不是宣称又完成了一次新的16项模型批次。视觉审核为 `ui_visual_review.md`。当前版本来源图为 `focused-source-graph-v2.png`，固定到2.0.0实际记录 `b727ecd1317c41711cd49c98` 的第2步阻断；旧 `focused-source-graph.png` 是1.0.0历史回放，不作为当前运行截图。

两次真实复验的运行 ID 分别是 `dc63325a33ec48fb816381f7842f45a9`、`f9d6607ec57344fcb8db119bb1c97ec0`。这些是交互验收运行，不计入正式 2.0 实验分母。自由对话没有预设完整答案时，界面继续显示“未自动评定”。

可重复浏览器检查脚本为 `frontend/scripts/browser_check.cjs`。不带参数检查实际页面布局，`--full` 执行真实本地模型流程；`--only=query_shortcut,upload_registered` 只复验指定检查。脚本保存唯一时间戳报告，既有失败不因后续复验被抹去。

## 演示录制接口

`scripts/record_v2_demo.cjs --plan` 只打印 240 秒七段计划，不录制。正式执行读取经复核的 `results/v2/demo_selection.json`：实时通知与上传使用真实 UI；三种防御配置对比读取固定真实记录；额外 `indirect_limit` 记录明确标注独立间接注入案例；生成页只展示真实生成预览；末段读取完成后的当前实验指标。

录制器不会注入页面正文或修改模拟状态，点击的是实际确认按钮。每段保存开始/结束时间、实际长度、是否超时、屏幕图像哈希、实时运行 ID 和回放记录 ID，最终保存原始视频 SHA256。实时、真实回放、样本预览与保存指标分别标记。原始视频需按真实时间段剪辑、加字幕并另行核验；脚本或计划本身不能算视频交付。

实际完整录制已完成，七阶段均达到目标时长，实时通知/上传各有真实运行ID。为使旁白指向可见的证据，另外通过 `--pickup indirect` 与 `--pickup results` 只读补录了网页污染正文→真实通知，以及v2_external的主表→消融→开销。补录不改变实验状态。原视频媒体时间与单调时钟的对齐、SHA256和精确裁切建议写在 `results/v2/browser/video_timing/timing_review.md`；最终MP4由交付编码流程另行验收，不把原始录像完成等同于最终视频验收。
