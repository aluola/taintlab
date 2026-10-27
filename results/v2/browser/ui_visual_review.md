# 2.0 对话界面视觉与证据核对

实际复核日期：2026-10-27（本地时间）。检查者为 AI 辅助开发代理，未代填任何小组成员工时。所有界面均为本地 Python 服务提供的生产 React 静态产物；没有注入 DOM 正文、伪造响应或更改实验状态。

当前验收总索引是 `ui_acceptance.json`。31 项前端组件/单元测试使用明确标记的夹具；真实浏览器功能证据按 16 个不同检查合并最新结果，来自首轮和针对性复测，不能写成一次全新的 16 项真实模型批次。原始失败仍保留。

| 实际打开并查看的图像 | 核对结论 |
|---|---|
| `desktop-home.png`、`laptop-home.png` | 三个主导航和四个快捷入口清晰；1366×768 无页面横向溢出。中文标题、参数入口和底部输入可读。 |
| `mobile-home.png`、`mobile-navigation.png` | 390×844 窄屏中输入框可见；导航折叠后内容可用。真实复测使用可见遮罩位置关闭导航，不把被侧栏覆盖的屏幕中心当作可点区域。 |
| `confirmation-pending.png`、`notification-delivered.png` | pending 与实际收件箱分开显示。真实确认后才出现通知；确认不是模型自然语言声明。 |
| `export-delivered.png`、`approved_export.txt` | 实际导出状态与下载入口可见；下载内容已在自动化验收中检查包含关键地点。 |
| `upload-registered.png`、`upload-completed.png` | 上传登记与授权读取是独立步骤。来源文本按纯文本展示，HTML 教学样例没有形成图片或外部请求。 |
| `focused-source-graph-v2.png` | 新图明确为 2.0.0 / `b727ecd1317c41711cd49c98`。所选第 2 步 `send_notification` 被 `recipient_not_granted` 拒绝；8 个相关节点来自完整 17 节点记录。说明明确为潜在影响，不能证明语义因果。 |
| `focused-source-graph.png` | 旧图属于在当前界面中打开的 1.0.0 历史记录；保留文件供追溯，不作为 2.0.0 运行截图引用。 |
| `attack-preview-indirect.png`、`attack-preview-segmented.png` | 注入前后来源和分段入口可见；预览与实际运行分开。 |
| `results-with-denominators.png`、`results-overhead.png` | 率与次数/分母同时显示；开销、接触率和失败状态另列，缺失数据不填成 0。图中版本按页面原标识解释。 |

最新窄屏复测：`ui_followup_2026-10-26T18-05-16-679Z.json`，3/3 通过，无 JavaScript 错误、无外部页面资源请求。初次失败的 `layout_check.json` 和 `layout_check_initial_transition_capture.json` 未覆盖。

当前来源图机器依据：`focused-source-graph-v2.json`，图像 SHA256 `d7636e7d44ae8af864633fab93929bb049ba6807f88f776760a30cfb14d086ad`。首次截图脚本路径/等待条件错误的记录仍保留；最终版本通过真实 UI 等待并捕获。

结论：上述指定画面的中文、布局和版本标注可读；没有发现遮挡关键操作或伪造状态。此核对不等于实体手机兼容性、所有浏览器认证或完整无障碍审计。自由对话仍可能遭遇模型任务失败，必须依据实际状态和独立评测解释。
