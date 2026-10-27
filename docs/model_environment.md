# 本地模型环境与准备记录

本文件记录项目实际采用的本地模型、下载来源、运行参数和验证证据。业务推理只允许访问 `127.0.0.1`；模型准备阶段访问官方 Hugging Face 和 GitHub 下载静态文件。模拟工具没有真实邮件、云模型或业务系统连接。

## 模型与推理程序

| 项目 | 固定值 |
| --- | --- |
| 模型 | Qwen3 0.6B |
| 权重仓库 | Qwen/Qwen3-0.6B-GGUF |
| 仓库 revision | 23749fefcc72300e3a2ad315e1317431b06b590a |
| 权重文件 | Qwen3-0.6B-Q8_0.gguf |
| 权重量化 | 官方 Q8_0 |
| 权重字节数 | 639446688 |
| 权重 SHA256 | 9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031 |
| 推理程序 | ggml-org/llama.cpp b11889 Windows x64 CUDA 13.4 |
| 服务地址 | http://127.0.0.1:8080 |
| 模型别名 | qwen3-0.6b |
| 单会话上下文 | 4096 tokens，服务端关闭 context shift，超限显式报错 |
| 并行槽位 | 4，总上下文 16384 tokens |
| 生成上限 | 每次请求 512 tokens |
| temperature 和 top_p | 0.2 和 0.9 |
| top_k 和 min_p | 40 和 0.05，固定版本服务端有效默认值 |
| 重复惩罚 | 1.0 |
| 思考模式 | 服务端 reasoning off；GGUF 内嵌 Jinja 模板 enable_thinking=false |

`configs/model.lock.json` 固定官方下载地址、revision、程序发布版本及每个下载包的 SHA256。`configs/model.json` 是应用配置。实验种子由评测器逐次传入；准备脚本内的独立冒烟使用 seed 17。不能把本地同种子结果视为跨硬件位级确定性保证。

## 当前平台

实际环境为 Windows 11 家庭版中文版 10.0.26200、Intel Core i7-13620H、16 GB 系统内存、NVIDIA GeForce RTX 4050 Laptop GPU。`nvidia-smi` 实测显存 6141 MiB、驱动 616.56。WMI 的 AdapterRAM 字段对该 GPU 报告约 4 GB，属于字段精度限制，因此资源预算采用 nvidia-smi 值。

完整采集值保存在 `results/environment/hardware.json`；内存空闲量和磁盘可用空间是采集时刻的快照，不是最低需求保证。推理、业务、评测无需 CUDA Toolkit；官方发布包包含所需 CUDA 用户态 DLL，需要兼容 NVIDIA 驱动。

## 可复现准备与启动

在项目根目录打开 PowerShell，推荐使用项目的 Python 虚拟环境；准备脚本只依赖 Python 标准库。

```powershell
.\.venv\Scripts\python.exe scripts/model_prepare.py
pwsh -File scripts/start_model.ps1
.\.venv\Scripts\python.exe scripts/model_health.py --smoke
.\.venv\Scripts\python.exe scripts/model_runtime.py
```

准备脚本并行下载固定权重、llama.cpp CUDA 程序包及 CUDA 运行库。采用 2 MiB HTTP Range 分块，每块检查 Content-Range 和长度，全部组装后与官方元数据中的 SHA256 比对。中断后重新运行同一命令会复用长度有效的分块，最终 SHA256 校验不能省略。若校验失败不会将文件标记为可用。

```powershell
.\.venv\Scripts\python.exe scripts/model_prepare.py --offline
.\.venv\Scripts\python.exe scripts/model_health.py
pwsh -File scripts/stop_model.ps1
```

`--offline` 不发起网络请求，核验本地权重、下载压缩包与解压后的程序清单。停止脚本只停止本项目 PID 文件记录且可执行文件路径相符的 llama-server，不会停止其他模型服务。进程使用隐藏窗口启动，日志分别写入 `results/environment/llama.stdout.log` 与 `llama.stderr.log`。

本机端口如被其他应用占用，不要终止未知应用。可用 `start_model.ps1 -Port 8081` 指定端口，并在应用配置中同步 endpoint，检查脚本使用 `--port 8081`。GPU 不兼容时可先用 `-GpuLayers 0` 定位问题；若正式实验切换硬件后端，应另行记录配置并完整重跑，不能混用性能结果。

## 实际准备问题与处理

2026 年 10 月 26 日，初次大文件顺序下载出现连接提前关闭，取得的文件长度小于官方长度，SHA256 校验失败。实现了有界分块、重试、断点复用和最终哈希验证，避免把短文件当成成功下载。GitHub `/releases/latest` 返回带 nightly-tag.txt 的版本标记，实际 Windows 二进制从官方发布列表选择固定的 b11889，并保存对应发布资产哈希。

## 验证证据

下载完成与真实推理验证后生成以下证据；文件存在且结果成功才代表通过：

- `results/environment/artifact_verification.json`：权重及运行包 SHA256、大小和校验时刻。
- `vendor/llama.cpp/verified_runtime.json`：解压程序逐文件 SHA256。
- `results/environment/model_health.json`：本机 health 与模型列表。
- `results/environment/model_smoke.json`：实际本地 JSON Schema 生成请求返回、解析动作、token 用量及耗时。
- `results/environment/model_runtime.json`：程序版本、服务器配置与 GGUF 内嵌聊天模板。

实际独立冒烟已于 2026 年 10 月 26 日通过：JSON Schema 约束下输出 `read_document(meeting)` 动作，输入 40 tokens、输出 38 tokens，端到端耗时 0.409 秒。服务器元数据给出实际参数量 596049920，build 指纹 `b11889-d854d98ba`。聊天模板 SHA256 为 `57f1fd00f0013a2be96aa79b857391f27e23df5b5f847072b524c897e24d0361`。四个槽位均为 4096 上下文，服务端 reasoning_format 为 none。所有权重、压缩包、已解压运行文件的离线哈希复核已通过。

该次准备冒烟仅验证结构化生成链路，其单次耗时不能作为整体任务性能结论；合法工具执行、注入攻击和防御效果必须由项目运行时的真实端到端实验判定。

## 官方参考

- [Qwen3 0.6B 模型卡](https://huggingface.co/Qwen/Qwen3-0.6B)
- [Qwen3 0.6B 官方 GGUF](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF)
- [llama.cpp 源码](https://github.com/ggml-org/llama.cpp)
- [固定版本发布页](https://github.com/ggml-org/llama.cpp/releases/tag/b11889)
- [固定版本服务器接口](https://github.com/ggml-org/llama.cpp/blob/b11889/tools/server/README.md)
- [结构化输出与 GBNF](https://github.com/ggml-org/llama.cpp/blob/b11889/grammars/README.md)

以上资源于 2026 年 10 月 26 日核查。官网模型卡建议的通用采样值与本项目冻结的小型结构化动作配置用途不同，报告以实际配置文件和请求日志为准。

## 视频工具准备

工作区捆绑运行时没有 FFmpeg。已通过 `scripts/prepare_video_tools.py` 下载并验证 FFmpeg 9.0.2 essentials Windows 构建，同时得到 ffmpeg、ffprobe 和 ffplay。该 Windows 分发者 Gyan Doshi 在 [FFmpeg 官方下载页](https://ffmpeg.org/download.html) 列出；固定包来自 [Gyan 构建页](https://www.gyan.dev/ffmpeg/builds/)。包 SHA256 为 `4705843ccaaf54257c16ad90f3e952ece33c17df964ecf7bfdbb0f49c7171077`。

```powershell
.\.venv\Scripts\python.exe scripts/prepare_video_tools.py
& .\vendor\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe -version
& .\vendor\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffprobe.exe -version
```

实际版本调用均成功，逐个可执行文件哈希见 `results/environment/video_tools.json`。该准备结果不代表演示视频已完成；视频时长、编码和实际画面验收由交付阶段单独记录。
