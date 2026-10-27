# 公开发布：首次安装与迁移核查事实

核查日期：2026-10-27。本文件记录安装脚本、固定资源及当前 Windows 验证边界；正式实验配置和结果没有因本次安装维护而改变。独立目录的安装、模型复用和实际启停结果将在完成后追加，不以计划代替验收。

## 1. 已核对的运行要求

| 项目 | 对外可准确表述的要求与边界 |
| --- | --- |
| 平台 | 日常 CMD、推理二进制与生命周期已针对 Windows x64 实现。当前实际主机 Windows 11 10.0.26200；其他操作系统未完成等效验收。 |
| Python | 安装脚本选择 CPython 3.12 x64；实际解释器为 3.12.10。项目元数据允许 `>=3.12,<3.14`，不等于 3.13 已完成安装和模型验收。 |
| uv / py / PATH | `uv` 可用时优先使用它；其默认行为可下载缺少的 Python 3.12。没有 uv 时依次尝试 `py -3.12` 和 PATH 上的 `python`，执行版本与 64 位检查后才创建环境。只有安装了 Python、却没有任何可发现命令的系统仍需修复 PATH 或安装 Windows Python Launcher。 |
| Python 环境 | 首次安装创建当前目录下的 `.venv`。已有可运行的 3.12 x64 venv 会复用并安装锁定依赖；非空的无效目录不会自动删除。跨目录迁移必须重新创建 venv，不复制旧 venv。 |
| NVIDIA | 固定下载为 llama.cpp b11889 Windows x64 CUDA 13.4，配套 CUDA 用户态 DLL；需要兼容的 NVIDIA GPU 和驱动。当前实际 RTX 4050 Laptop，6141 MiB 显存，驱动 616.56。没有测定最低显存、最低内存或所有兼容驱动，不把该实测配置写成普遍最低要求。 |
| CUDA 工具链 | 日常运行使用预编译程序及其 DLL，不编译 CUDA 源码，不要求安装完整 CUDA Toolkit、Visual Studio 或 npm 开发服务器。NVIDIA 驱动仍为系统前置条件。 |
| 内存与磁盘 | 当前主机系统内存 16 GB。建议首次准备至少预留 5 GB 可用空间，覆盖锁定文件、解压运行库、Python 依赖、缓存和下载分块；这是保守规划值，不是最低需求测量。 |
| 网络 | 第一次准备依赖和模型允许联网；默认双击启动不会自动下载。日常页面、API 与模型仅在本机回环地址运行。离线验收的应用通信守卫不等于整机物理断网。 |
| Node / FFmpeg | 已随源码提供 Vite 生产产物，日常启动不需要 Node。Node 仅用于重建前端与开发测试；FFmpeg 仅用于重新制作或验证媒体，不属于 Agent 业务启动依赖。 |

uv 官方文档说明其可以发现已有 Python，也可自动下载所需版本；通过 uv 获得的解释器来自 python-build-standalone，而非声称来自 Python.org Windows 安装器。Python 官方 Windows 文档分别说明了 `py` 启动器及 PATH 选项。[uv 的 Python 管理说明](https://docs.astral.sh/uv/guides/install-python/)、[Python 3.12 Windows 说明](https://docs.python.org/3.12/using/windows.html)。

NVIDIA CUDA 13.4 发行说明列出 R615 对应驱动分支，也说明 13.x 的次版本兼容有条件支持更早驱动。发布文档应给出本项目实际驱动 616.56 和兼容性要求，不能仅依据通用兼容表声称某个较低驱动已运行本固定构建。[NVIDIA CUDA 13.4 发行说明](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/index.html)。

## 2. 固定下载量与核验

以下三项在 2026-10-27 从现有文件重新计算长度和 SHA256，全部符合 `configs/model.lock.json`。两个 ZIP 的长度和 digest 还与当天官方 GitHub b11889 API 返回值核对一致；该 release 标记为 pre-release，未将其称为稳定版最新版。

| 文件 | 下载字节数 | SHA256 |
| --- | ---: | --- |
| Qwen3-0.6B-Q8_0.gguf | 639,446,688 | `9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031` |
| llama-b11889-bin-win-cuda-13.4-x64.zip | 164,718,677 | `2001a5f37de39dced918cfb8d5b8f699822137c85cf58cb1a0d97e530f4f3363` |
| cudart-llama-bin-win-cuda-13.4-x64.zip | 423,535,356 | `738f8c251ac22b70c3ae6f83a10cf222725df0395246a2cf58f32bdb85fbe668` |
| 合计 | **1,227,700,721** | 约 **1.1434 GiB**，或十进制 **1.2277 GB** |

两个 ZIP 的未压缩文件合计 765,604,461 字节。本机原 `.venv` 逻辑文件总量 374,900,560 字节，仅供磁盘规划参考，不能当作依赖下载量。上述 1.1434 GiB **不包含** Python 解释器、Python 包、GitHub 源码包或可选视频工具；这些网络开销受已有缓存、解释器来源、平台和安装方式影响，本轮没有伪称为统一固定总数。

模型 revision 为 `23749fefcc72300e3a2ad315e1317431b06b590a`。程序固定官方 [llama.cpp b11889 发布页](https://github.com/ggml-org/llama.cpp/releases/tag/b11889)；权重固定 [Qwen 官方 GGUF 仓库](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/tree/23749fefcc72300e3a2ad315e1317431b06b590a)。所有完整下载 URL 在模型锁文件，不使用运行时 latest。

`model_prepare.py` 在组装文件后对完整 SHA256 进行校验，分块长度检查不能代替此校验。`--offline` 验证已有权重和两个 ZIP；如果是新目录且没有解压清单，会从这些已验证 ZIP 解压并生成逐文件清单。只复制权重和 `llama-server.exe` 不构成完整准备：还需其 DLL，并且离线准备命令仍要求两个锁定 ZIP 存在。

证据：`results/publication/installation_inventory.json`、`results/publication/official_runtime_metadata.json`。本次检查复用了既有文件，并未再次下载 1.14 GiB。

## 3. 对外首次运行命令

先解压项目到可写的新目录，在项目根目录打开 Windows PowerShell。推荐路径保持较短；本轮回归会覆盖中文和空格，不依赖原开发目录。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install.ps1
.venv/Scripts/python.exe scripts/model_prepare.py
.venv/Scripts/python.exe scripts/model_prepare.py --offline
```

然后双击根目录 `启动项目.cmd`，健康后会打开 `http://127.0.0.1:8501/`；停止使用 `关闭项目.cmd`。无管理员权限也可以安装到用户可写目录，但系统驱动的安装权限另行适用。首次安装失败应先解决错误后重试，不要通过复制原目录 `.venv` 绕过安装。

安装脚本用锁文件安装依赖，再以 `--no-deps --no-build-isolation -e .` 安装当前目录项目，并运行依赖一致性检查。uv 模式中 uv 缺省会使用本机缓存；没有 uv 的分支通过 `ensurepip` 本地准备 pip 后安装同一锁文件。

可选 `-Venv <路径>` 供安装验证使用，但日常 CMD 固定使用项目根目录 `.venv`，不能给用户暗示 CMD 会自动使用任意环境目录。没有联网与可用缓存时，第一次准备不会凭空成功；应在可联网环境完成准备或按锁迁移完整资源。

## 4. 迁移验收步骤与准确边界

1. 从主代理指定的公开仓库或发布资产下载到独立目录，记录 URL、提交或资产哈希，不从工作区拷贝源码冒充远程下载。
2. 在新目录运行上述实际 `scripts/install.ps1` 默认命令，创建自己的全新 `.venv`。不复制已有环境；包缓存可以复用并明确记录。
3. 核对原权重和两个官方 ZIP 的锁定哈希，复制到新目录同名相对位置，再核对目标哈希。新目录运行 `model_prepare.py --offline`，从已认证 ZIP 建立自己的推理文件。此步骤是已有静态文件哈希复用，不是全新网络下载。
4. 原服务截图结束且主代理授权切换后，用原目录正常关闭 CMD 关闭其已核验身份的服务。再从新目录 CMD 启动，检查模型和 UI 的完整程序路径、参数、创建时间、监听端口归属及 HTTP 健康。
5. 在独立浏览器里完成真实业务任务，核对实际模拟状态。检查重复启动、关闭、重复关闭和关闭后重启；不终止未知端口进程。
6. 保存安装日志、解释器和模块路径、资源逐项哈希、生命周期结果及真实任务证据。明确这是同一 Windows 主机的新源码目录和新 venv，不能声称是新安装的操作系统、另一台硬件或全程无缓存首次下载。

本轮开始时原工作区 8080 和 8501 均未监听。已实际经根 CMD 正常恢复且两项身份与健康检查通过；证据为 `results/publication/original_initial_status.json`、`original_started_status.json` 和 `original_start_console.log`。这只证明原目录本轮恢复，不提前算作独立迁移验收完成。

## 5. 安装脚本维护与回归

本轮只改安装边界：无 uv 时的 Python PATH 回退、3.12 x64 检查、现有 venv 复用和无效目录保护，以及安装后依赖一致性检查。没有改模型锁、采样参数、Agent 或正式评测语义。

`tests/test_installation.py` 在临时中文及空格路径中执行实际 PowerShell 脚本，真实创建 venv；包安装调用使用明确的隔离夹具，禁止网络与服务操作。覆盖 uv、Windows py、PATH python、重复安装保留文件、无效目标、缺失或错误解释器和锁安装失败后不继续。真实依赖安装由独立目录验收另行证明，不能把这些夹具测试当作真实安装结果。

最终该组回归实际 **8 passed in 55.97s**；JUnit 为 `results/publication/pytest_installation.xml`。这不是全仓库测试总数。

开发过程中 PowerShell 5.1 对嵌入 Python 命令中的双引号处理导致版本检查失败，已改为对原生参数安全的单引号表达式；同时显式把版本 `3.12` 作为字符串传给 uv，避免 PowerShell 数值转换。首次失败与修复后的回归结果单独保存在 `results/publication/`，未覆盖历史版本验收。

## 6. 已完成的独立目录预验

2026-10-27 在 `D:\taintlab-publication-preflight-20261027` 完成预验。该目录由当前工作区的运行白名单复制得到，**不是公开仓库重新下载，也不是最终 Release 包验收**。

- 实际执行默认 `scripts/install.ps1`，环境变量 `UV_OFFLINE=1`：新建自己的 `.venv`，真实安装 67 个锁定包和当前目录的 taintlab 2.0.0；68 包一致性检查通过。使用原机 uv 缓存，没有复制原 `.venv`，没有重新下载依赖。跨磁盘不能硬链接时 uv 自动退回文件复制，安装成功。
- 新解释器和 `taintlab.__file__` 均指向独立目录。复制的 GGUF 与两个 ZIP 在源、目标两端都与锁定长度和 SHA256 一致；在新目录实际执行 `model_prepare.py --offline`，重新解压其推理程序与 DLL。没有声称从网络重新下载这些资源。
- 正常关闭原项目后，实际通过 Windows 文件关联执行新目录 CMD，并检查该目录自己的模型、UI 程序与完整参数、创建时间、监听归属及 HTTP 健康。重复启动保留原进程、关闭、重复关闭和关闭后重启均通过。自动调用文件关联不等于人手鼠标双击。
- 独立无用户配置的 Playwright 浏览器实际运行四项任务，全部使用 `local_llama_cpp`：会议读取、项目日期查询、通知待确认后刷新恢复并确认入箱、导出待确认后确认并下载真实导出内容。四项均通过，浏览器错误为 0，外部请求为 0。确认点击是自动化验收行为，不记作成员人工工作量。
- 通知待确认图和导出交付图分别以 original 尺寸人工检查，目标、正文和确认/下载按钮可读；没有改写页面状态或模型结果。
- 11 项生命周期和证据检查全部通过。最后关闭预验服务、恢复原项目模型和 UI 健康；3779 个受保护文件前后聚合哈希一致，包含旧 1296 条及当前 2376 条正式原始记录。

| 真实任务 | run_id | 结果 |
| --- | --- | --- |
| 会议读取 | `f96a67b5f33947d5a44cada23837240d` | `completed`，实际读取 meeting，含周三15:00/A301 |
| 日期查询 | `0205a982534d409096c763bc33c7b035` | `completed`，实际 search_info，含11月3日/11月8日 |
| 通知确认 | `4dfc76540dac4d3eafb9d6b27abb975a` | 确认前收件箱为空，确认后 team_A 有1条含A301通知，最终 completed |
| 文件导出 | `c0ac44cbc9aa40d18c85cb6b6b3bba1a` | 确认前文件为空，确认后1个虚拟文件，实际下载正文含A301 |

证据索引：`results/publication/preflight_source_copy.json`、`preflight_install.json`、`preflight_resource_reuse.json`、`preflight_artifact_verification.json`、`preflight_windows.json`、`preflight_browser.json`、`preflight_approved_export.txt`、`preflight_visual_review.json`。完整日志和两张抽查图位于同目录。本次没有重新安装 Windows，也没有修改系统联网或测试其他 GPU；实际公开下载验收另行记录，不能由本节替代。
