# 2.0 对话版实施计划

开始：2026-10-27（Asia/Shanghai）。实际基线HEAD为5c2a75c，初始工作区干净，不回退历史。

| 阶段 | 交付与核验 | 当前状态 |
|---|---|---|
| 现状与参考 | 核心/接口/启动器审查、外部固定revision和数据许可 | 已完成 见UI_REFERENCE与DATA_SOURCES |
| 安全服务 | FastAPI、服务器会话、任务授权、上传、SSE、确认/停止、审计投影 | 已实现并真实API及安全回归验证 |
| 对话界面 | React/TS/Vite三入口、工具卡、来源及权限详情、前端构建 | 已实现并实际浏览器复核，31项前端测试通过 |
| 数据扩展 | 两公开来源、60攻击+30正常、13开发样本、生成与冻结 | 已冻结并离线校验 |
| 新版实验 | 52开发实测后冻结；108旧集+90扩展、4模式、3种子，共2376次 | 全部完成且50项独立复算检查通过 |
| 端到端 | 浏览器、Windows生命周期、隔离安全测试、来源与Canary对照 | 真实API及浏览器；18项Windows启停通过；实际离线守卫3项任务通过；测试最终数字见JUnit |
| 媒体与文档 | 新界面180–300秒Demo、MD/DOCX/PDF排版QA | 240秒成片、中文旁白字幕、浏览器播放检查完成；24页报告逐页检查完成 |
| 最终发布门槛 | 新轻量包、逐文件SHA、独立解压与全新venv运行 | 执行脚本固定为build_package、verify_light_package、verify_offline_v2；最终包绑定验收记录位于dist/light_package_validation.json、light_package_runtime_validation.json和release_receipt_v2.json，不把包生成前的静态检查当作安装结果 |

记录实际证据，不把计划当作完成。旧results/main、ablation、data正式文件及完整包保留；新运行写results/v2。旧结论注明对应版本。成员真实信息与工时仍待补充。主代理负责核心/服务集成与验收，界面、公开数据、生命周期分边界协作，不共同修改同一核心文件。
