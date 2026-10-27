# 2.0 对话版 Windows 启停验收

日期2026-10-27（Asia/Shanghai）。旧版验收保存在docs/history/LAUNCHER_ACCEPTANCE_5c2a75c.md；不使用其测试数字证明新版服务可用。本轮保留两个根目录CMD，将界面从Streamlit迁移为Python FastAPI同时提供React静态页面与API。

## 日常行为与归属检查

双击“启动项目.cmd”检查项目虚拟环境、依赖、配置、模型和前端构建产物。它以自身目录定位，模型HTTP健康后启动或复用界面，打开127.0.0.1:8501。服务在后台独立运行，关闭启动窗口不会关闭项目。双击“关闭项目.cmd”先停止已确认身份的界面，再停止本项目模型，重复关闭正常结束。没有每次安装依赖、下载模型或修改全局执行策略。

身份依据是可执行路径、完整参数、项目脚本/模型路径、父子进程和创建时间，并与监听和HTTP接口交叉检查。Windows venv转发父进程和实际持端口子进程一起核验。旧PID、同名python/llama-server或占用相同端口均不单独构成终止权限。并发启动受项目命名互斥量保护；失败回滚仅触及本次创建且重新确认身份的进程。

新UI健康接口是/api/health，要求service=taintlab-web、version=2.0.0。旧Streamlit可以识别并关闭，但不能当作新UI健康服务。start_ui.ps1为FastAPI前台调试入口，Ctrl+C退出；日常使用CMD。

日志、运行状态和错误写results/v2/launcher，不覆盖历史results/launcher或正式实验。状态文件不进入轻量包。错误窗口保留并显示修复命令；未知端口占用者只报告冲突，不误杀其他Python、模型、终端或浏览器。

## 实际 Windows 检查

results/v2/launcher/validation/actual_windows_validation.json记录18项实际检查全部通过。通过Windows ShellExecuteEx激活实际根目录CMD，与资源管理器双击采用同一文件关联入口；没有声称人工鼠标手势。工作目录故意设为其他目录，项目实际路径含中文与空格。

| 检查 | 本轮实际结果 |
| --- | --- |
| 无服务冷启动 | 模型8080和新UI8501都健康 |
| 启动器退出 | 服务PID、创建时间及HTTP仍有效 |
| 连续与并发启动 | 复用相同服务，无重复 |
| 关闭、重复关闭、再启动 | 自有服务退出；重复关闭正常；重启健康 |
| start_ui.ps1原入口 | 实际启动FastAPI并由CMD正确识别关闭 |
| 模型端口与UI端口分别由无关监听占用 | 启动拒绝；关闭项目不会结束无关进程 |
| 缺虚拟环境 | 隔离目录准确报缺失及修复命令，没有破坏安装 |
| 数据保留 | 3779个受保护文件前后聚合SHA一致，含全部3672正式原始记录 |

主18项流程开始时已没有旧Streamlit实例，所以其中迁移子分支标记未执行。本轮较早确实从旧Streamlit迁移的证据另存ui_migration.json，不能用主流程未执行的分支冒充通过。

模型离线提示另外实际停止本项目模型，保持UI进程不变，在真实浏览器检查离线状态，再重启并检查恢复。证据为results/v2/browser/model-offline-lifecycle.json及离线、恢复截图。结束后模型和界面均恢复健康。

陈旧PID、身份不符、PID重用、坏配置、有界等待、回滚竞争与确认并发等由隔离程序测试覆盖，和真实服务流程分别报告。全量当前数字见results/v2/validation/pytest.xml；不再引用历史185项作为本轮结果。

## 复现

```powershell
.venv/Scripts/python.exe scripts/project_lifecycle.py status
# 以下验证会短暂停止本项目服务，然后恢复；勿与正在运行的任务并行
.venv/Scripts/python.exe scripts/verify_launcher_windows.py --execute
.venv/Scripts/python.exe scripts/verify_model_offline_windows.py --execute
.venv/Scripts/python.exe -m pytest -q
```

其他操作系统和硬件、人工鼠标双击手势未完整验证。进程身份检查防止误杀与陈旧状态，不宣称能防御可伪造同权限进程的本机恶意软件。服务实际PID随重启改变，以status和时间戳记录为准。
