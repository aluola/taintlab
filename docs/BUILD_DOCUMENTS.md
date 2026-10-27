# 文档与图像构建说明

发布 v2.0.1 的两份专题文档由 Markdown 生成，运行核心仍为 2.0.0。普通用户下载已有 PDF/DOCX 即可；日常使用不需要安装文档排版工具。

## 本次实际使用的独立排版环境

本轮在 Codex 提供的独立 Python 文档环境运行 `scripts/build_feature_documents.py`，使用 python-docx 1.2.0、Pillow 12.3.0、pypdf 6.10.0、lxml 6.1.1。项目业务 `.venv` 没有 python-docx，因此不能把业务安装完成等同于文档构建环境已准备。DOCX 转 PDF 使用项目专用的便携 LibreOffice 和文档渲染脚本；没有自动控制用户已打开的 Word 文档。

可以在额外的文档虚拟环境安装上述固定版本，然后执行：

```powershell
python scripts/build_feature_documents.py --document all
```

此命令只生成 DOCX。架构图可单独用 `--architecture-only` 重建；它是程序绘制的结构示意，不是应用截图。中文字体要求 Windows Microsoft YaHei。保留 Markdown、原截图、标注配置和源图，不使用生成式图片补画业务结果。

## PDF 与逐页验收

自动渲染使用 `--render`；需通过 `TAINTLAB_DOC_RENDERER` 指向文档渲染脚本、`TAINTLAB_SOFFICE` 指向专用便携 `soffice.exe`、`TAINTLAB_DOC_RUNTIME` 指向带 Poppler 的依赖目录。默认路径仅是本次作者环境的便利定位，不是终端用户安装要求；这些外部排版工具不进入轻量包。

没有相同渲染工具时，可在独立的 LibreOffice 中打开生成的 DOCX，导出 PDF，再逐页检查；这条替代方式没有在本轮另做独立安装验证，不能据此复用已有视觉验收。

每次改动 Markdown、DOCX、PDF 或截图后，原 QA 哈希即失效。渲染不等于目视通过：必须检查全部页面的字体、图中文字、标注编号、分页、表格换行和页码，记录新的 `visual_review.json` 后，再执行：

```powershell
.\.venv\Scripts\python.exe scripts/verify_feature_documents.py --document all
```

验证器检查六章顺序、相对链接、DOCX 结构、PDF 可读性及逐页视觉记录的 SHA256。它不会自动制造人工或 AI 视觉批准。当前验证记录分别位于 `docs/core_features_qa/` 和 `docs/development_delivery_qa/`；中间全页渲染图不进入轻量包。

综合使用手册仍使用 `scripts/build_user_manual.py`，其本轮导航增补与新 QA 独立于 v2.0.0 的原版操作截图。Demo 录制、旁白、字幕和剪辑复现见 [demo/README.md](../demo/README.md)。
