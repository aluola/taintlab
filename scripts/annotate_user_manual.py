"""Deterministic user-manual crops/numbered rectangles; never invent UI pixels.

Run with Python 3.11+ and Pillow. It chooses the latest actual capture for each
figure, verifies its hash, and preserves all original takes and failure notes.
Daily project execution does not need this optional publishing dependency.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets" / "user-manual"
PADDING = 28
COLOR = "#b65e24"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def font():
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arialbd.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), 16)
    return ImageFont.load_default(size=16)


def annotate(original: Path, output: Path, spec: dict) -> dict:
    with Image.open(original) as source:
        source = source.convert("RGB")
        x, y, width, height = spec["crop"]
        assert 0 <= x < x + width <= source.width
        assert 0 <= y < y + height <= source.height
        cropped = source.crop((x, y, x + width, y + height))
    canvas = Image.new("RGB", (width + 2 * PADDING, height + 2 * PADDING), "white")
    canvas.paste(cropped, (PADDING, PADDING))
    draw = ImageDraw.Draw(canvas)
    labels = []
    for number, mark in enumerate(spec["marks"], 1):
        left, top, right, bottom = mark["rect"]
        assert x <= left < right <= x + width, (output.name, mark)
        assert y <= top < bottom <= y + height, (output.name, mark)
        box = [left - x + PADDING, top - y + PADDING,
               right - x + PADDING, bottom - y + PADDING]
        draw.rectangle(box, outline=COLOR, width=2)
        # The badge is outside the highlighted rectangle. Added white padding
        # prevents edge clipping without replacing any screenshot content.
        cx, cy, radius = box[0] - 14, box[1] + 12, 11
        if "badge_center" in mark:
            cx, cy = mark["badge_center"][0] - x + PADDING, mark["badge_center"][1] - y + PADDING
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                     fill="white", outline=COLOR, width=2)
        draw.text((cx, cy), str(number), font=font(), fill=COLOR, anchor="mm")
        labels.append({"number": number, "label": mark["label"],
                       "shape": "outline_rectangle_with_number",
                       "original_rect": mark["rect"], "output_rect": box,
                       "output_badge_center": [cx, cy], "color": COLOR,
                       "width_pixels": 2, "fill": None})
    canvas.save(output)
    return {"path": rel(output), "sha256": sha(output),
            "width": canvas.width, "height": canvas.height,
            "crop": spec["crop"], "padding_pixels": PADDING,
            "annotations": labels,
            "crop_note": spec.get("crop_note"),
            "capture_note": spec.get("capture_note")}


def main() -> None:
    config_path = ASSETS / "annotation_config.json"
    config = read(config_path)
    chosen, takes, errors, downloads = {}, [], [], []
    for manifest in sorted((ASSETS / "captures").glob("*/capture_manifest.json")):
        data = read(manifest)
        takes.append({"path": rel(manifest), "sha256": sha(manifest),
                      "captured_at_utc": data.get("captured_at_utc"),
                      "figure_count": len(data.get("figures", [])),
                      "errors": data.get("errors", [])})
        for fig in data.get("figures", []):
            chosen[fig["id"]] = fig
        if data.get("download"):
            downloads.append({**data["download"], "local_only": True,
                              "included_in_public_package": False,
                              "public_note": "实际合成文本下载只保留在本机取证take；公开包保留字节数、哈希和内容断言元数据。"})
        for error in data.get("errors", []):
            errors.append({"take": rel(manifest), **error})
    # Optional actual native-window capture supplied by the parent reviewer.
    # Expected schema is one complete figure object, or {"figures": [...]}.
    for extra in sorted(ASSETS.glob("*.metadata.json")):
        data = read(extra)
        for fig in data.get("figures", [data]):
            chosen[fig["id"]] = fig

    raw_dir, out_dir = ASSETS / "raw", ASSETS / "annotated"
    raw_dir.mkdir(exist_ok=True)
    out_dir.mkdir(exist_ok=True)
    figures = []
    for ident, spec in sorted(config["figures"].items()):
        if ident not in chosen:
            raise ValueError(f"No actual screenshot for {ident}")
        fig = dict(chosen[ident])
        original = ROOT / fig["raw_path"]
        assert sha(original) == fig["raw_sha256"], f"Original changed: {ident}"
        stable_raw = raw_dir / (ident + ".png")
        if original.resolve() != stable_raw.resolve():
            shutil.copyfile(original, stable_raw)
        fig["original_take_path"] = fig["raw_path"]
        fig["original_take_in_public_package"] = False
        fig["raw_path"] = rel(stable_raw)
        fig["stable_raw_path"] = rel(stable_raw)
        fig["annotation"] = annotate(original, out_dir / (ident + ".png"), spec)
        # The capture-time suggested box is superseded by the visually reviewed
        # publishing crop. Preserve it as evidence rather than silently discard it.
        fig["capture_suggested_crop"] = fig.pop("crop", None)
        fig["capture_suggested_annotations"] = fig.pop("annotations", [])
        figures.append(fig)

    index = {
        "project_version": "2.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "figure_count": len(figures),
        "figures": figures,
        "takes": takes,
        "actual_downloads": downloads,
        "preserved_failures": errors,
        "known_model_failure": {
            "run_id": "10425d2a4dfd456e8ee1c804e104d8d6",
            "screenshot_local_only": "docs/assets/user-manual/captures/2026-10-27T01-43-21-699Z/failure_upload.png",
            "public_package_note": "失败元数据保留，截图属于本机原take，公开包不含重复或失败take像素。",
            "observed": "首次TXT任务直接回复‘任务结果’，没有调用read_document；未通过读取与内容断言。",
            "retest": "图11为第二次独立运行，显式要求先调用read_document后，实际读取并回答B202与10:30。",
        },
        "boundaries": [
            "实际页面截图，未注入DOM、模拟响应或改写正式实验状态。",
            "方框与编号为确定性Pillow标注；裁切不改变UI内容。完整原图和所有失败尝试保留。",
            "图10为独立上传登记补拍，未调用模型；与图11不是同一文档ID或运行。",
            "预览图15–18仅证明规则生成预览可操作，不是模型攻击成功或新增正式实验。",
            "图12–14为当前2.0真实冻结记录回放；图21为明确标记的1.0历史回放。",
            "自然语言任务显示‘未自动评定’，本取证脚本另核查模拟状态和关键内容，不能把模型自述当完成。",
            "当前回放案例合法任务未完成，未读取Canary也不能归因于信息流防御。",
            "没有导出活跃会话数据库、所有者令牌、Cookie或Canary原值。",
            "公开包保留raw/最终原图、annotated/标注图及每轮capture_manifest.json；captures中的重复原take PNG只保留在本机。每张最终raw的SHA256与所选原take完全一致。",
            "图13聚焦所选动作，图的横向范围可滚动；该截图不是完整因果图，也不展示模型内部思维。",
        ],
        "reproduction": {
            "capture": "node scripts/capture_user_manual.cjs",
            "registration_only": "node scripts/capture_user_manual.cjs --only=upload --registration-only",
            "native_directory": "node scripts/capture_user_manual.cjs --only=project_files (installed Edge, or TAINTLAB_NATIVE_CHANNEL)",
            "annotate": "python scripts/annotate_user_manual.py",
            "browser_dependency": "scripts/browser_dependencies.cjs uses environment variables, installed Playwright, and browser-cache discovery.",
            "config": rel(config_path), "config_sha256": sha(config_path),
            "script": "scripts/annotate_user_manual.py", "script_sha256": sha(Path(__file__)),
        },
        "visual_review": "required after annotation generation",
    }
    write(ASSETS / "figure_index.json", index)
    write(ASSETS / "capture_manifest.json", index)
    lines = ["# 用户手册截图索引", "", "此文件由 annotate_user_manual.py 从实际截图记录生成。所有截图均保留完整原图；注释只添加方框和编号。", ""]
    for fig in figures:
        lines += [f"## {fig['id']}｜{fig['title']}", "",
                  f"- 标注图：`{fig['annotation']['path']}`",
                  f"- 原图：`{fig['stable_raw_path']}`",
                  f"- UTC：{fig['captured_at_utc']}；版本：{fig['version']}；类型：{fig['live_or_replay']}",
                  f"- 运行：`{fig.get('run_id') or '无（界面/规则预览）'}`；案例：`{fig.get('case_id') or '无'}`",
                  f"- 观察结果：{fig['observed_result']}", "", "操作：", ""]
        lines += [f"{i}. {step}" for i, step in enumerate(fig.get("steps", []), 1)]
        lines += ["", "编号：", ""]
        lines += [f"{a['number']}. {a['label']}" for a in fig["annotation"]["annotations"]]
        lines += ["", f"原图SHA256：`{fig['raw_sha256']}`", ""]
    lines += ["## 失败、复测及范围", "", index["known_model_failure"]["observed"],
              index["known_model_failure"]["retest"], ""]
    lines += [f"- {x}" for x in index["boundaries"]]
    (ASSETS / "FIGURES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"figures": len(figures), "index": rel(ASSETS / "figure_index.json"),
                      "all_capture_assertions_passed": all(f.get("assertions_passed") for f in figures)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
