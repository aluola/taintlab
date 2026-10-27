# 首次公开发布说明与验收边界

仓库：[aluola/taintlab](https://github.com/aluola/taintlab)；正式发行入口：[v2.0.0](https://github.com/aluola/taintlab/releases/tag/v2.0.0)。本轮只维护安装发现、制作工具路径、公开白名单与文档，未改变2.0模型、冻结数据、策略、攻击判定或正式实验分母。

## 内容与来源

原项目来源基线为 `0c855a0cb756669e098d5bc5ac576cbd36aea685`。保留原本地仓库，在独立白名单目录提交公开快照；最终源提交、逐文件来源哈希与投影差异记录在仓库根 `PUBLICATION_MANIFEST.json`。公开Git只包含该快照的可追溯历史，不上传旧环境日志。此前可达历史5提交、302唯一blob均经只读扫描与候选人工复核；没有未解决的真实凭据候选，不宣称该扫描证明所有秘密不存在。

正式3672条原始模拟记录、指标、必要回放、生产界面、模型锁、CMD、Demo、报告与本手册保留。活跃会话/上传资料、凭据、模型权重、推理二进制、venv、node_modules、PID和原始录屏排除。详细规则见 [PUBLICATION_POLICY.md](PUBLICATION_POLICY.md)。本轮没有重新运行2376次当前正式实验。

## 发布前实际验收

| 项目 | 本轮实际结论 |
| --- | --- |
| 安装脚本隔离分支 | 8项通过；真实PowerShell和临时新venv，包管理调用为明确测试夹具 |
| 独立目录依赖安装 | 实际运行 README install.ps1，新建venv，67锁定包加项目共68包一致性检查通过；UV_OFFLINE=1复用既有uv缓存，没有复制旧venv |
| 模型资源准备 | 三个固定文件共1,227,700,721字节，复制前后SHA符合锁；在新目录执行 model_prepare.py --offline 解压，不冒称重新联网下载 |
| 自有模型/UI与启停 | 11项检查通过；路径、argv、创建时间、监听端口与健康同时核验，冷启、重复启动、关闭、重复关闭、重启和原服务恢复 |
| 浏览器业务 | 4项真实本地模型任务通过：读取、查询、通知确认及刷新恢复/实际入箱、导出确认/真实下载；浏览器错误及外连均0 |
| 证据保留 | 3779个受保护文件前后哈希一致，其中3672条正式记录全部保留 |
| 现有Demo复核 | 原MP4保持不变；240秒、1600×900、H.264 yuv420p/AAC；全文件解码通过，6个真实浏览器播放点无错误 |

上述预验使用当前工作区的运行白名单复制目录，**不是远程Release下载验收**。公开摘要在 `results/publication/`，其 source_evidence_sha256 / original_evidence_sha256 指向本机详细记录；摘要明确标记，不伪称完整原始日志。安装事实详见 [INSTALLATION_FACTS.md](INSTALLATION_FACTS.md)。

## 公开发布与远程验收的分工

发布按“检查原件→准备新快照→精确git add及索引字节核验→提交/tag→在快照构建轻量包→Release附件→匿名下载”执行。公开库的 `.gitattributes` 末尾固定字节，避免Windows换行转换破坏清单；差异在发布清单中声明。ZIP不进入Git历史，最终视频直接跟踪，无Git LFS门槛。

发布后的实际匿名获取、SHA/长度、解包清单、远程目录全新环境与自有进程、实际业务及最终服务恢复，单独记录为 Release 附件 `PUBLIC_DOWNLOAD_ACCEPTANCE.json` 及随附说明。该附件只在实际完成后上传；它不回写ZIP，不修改已发布tag或先前附件。仅有API创建回执不等于下载验收通过。

下载文件的 `SHA256SUMS` 使用附件同级文件名：PowerShell `Get-FileHash .\taintlab_project_light.zip -Algorithm SHA256` 后对照。包内 `DELIVERY_MANIFEST.json` 记录逐文件哈希；外部 `light_manifest.json` 同时记录ZIP哈希及源提交。GitHub生成源码ZIP另有字节，不与手工轻量包混比。

## 版本与真实限制

公开2.0继承已冻结结果而非再次生成：历史1296、当前2376。扩展完整策略ASR34/180高于无防御31/180；污点独立安全收益未证实；三主配置含无防御均零Canary外泄；当前没有完整策略阻断后安全完成全部合法任务的成功实例。正常完成的确认辅助与自动分别统计。自有许可证和成员姓名、学号、真实分工/工时仍待作者补充。
