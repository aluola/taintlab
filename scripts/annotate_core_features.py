"""Select real captures and add reproducible rectangles, arrows and numbers.

Only cropping, a white annotation margin, and programmatic marks are applied.
No screenshot content is generated, retouched, or replaced.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/assets/core-features"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def arrow(draw, start, end, color, width=3):
    draw.line([start, end], fill=color, width=width)
    angle = math.atan2(end[1]-start[1], end[0]-start[0])
    size = 9
    wings = [(end[0]-size*math.cos(angle+turn), end[1]-size*math.sin(angle+turn)) for turn in (-0.55, 0.55)]
    draw.polygon([end, *wings], fill=color)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="append")
    args = parser.parse_args()
    manifests = args.manifest or sorted((ASSETS/"captures").glob("*/capture_manifest.json"))
    if not manifests:
        raise SystemExit("No actual captures exist")
    selected, takes = {}, []
    for file in manifests:
        data = json.loads(file.read_text("utf8"))
        takes.append({"path": file.relative_to(ROOT).as_posix(), "sha256": sha(file), "errors": data.get("errors", [])})
        for item in data.get("figures", []):
            selected[item["id"]] = {**item, "capture_manifest": file.relative_to(ROOT).as_posix()}
    for name in ("raw", "annotated"):
        (ASSETS/name).mkdir(parents=True, exist_ok=True)
    overrides_path=ASSETS/"annotation_overrides.json"
    overrides=json.loads(overrides_path.read_text("utf8")) if overrides_path.is_file() else {}
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 23) if font_path.is_file() else ImageFont.load_default()
    entries, configurations = [], {}
    for ident, source in sorted(selected.items()):
        source={**source,**overrides.get(ident,{})}
        original = ROOT/source["raw_path"]
        if sha(original) != source["raw_sha256"]:
            raise ValueError(f"Capture hash changed: {ident}")
        raw = ASSETS/"raw"/(ident+".png")
        shutil.copy2(original, raw)
        image = Image.open(raw).convert("RGB")
        c = source["crop"]
        bounds = (int(c["x"]), int(c["y"]), int(c["x"]+c["width"]), int(c["y"]+c["height"]))
        if bounds[0]<0 or bounds[1]<0 or bounds[2]>image.width or bounds[3]>image.height:
            raise ValueError(f"Crop outside actual capture: {ident}")
        cropped = image.crop(bounds)
        margin = 48
        canvas = Image.new("RGB", (cropped.width+margin*2, cropped.height+margin*2), "white")
        canvas.paste(cropped, (margin,margin))
        draw = ImageDraw.Draw(canvas)
        color = "#b65f22"
        marks, occupied = [], []
        for mark in source["annotations"]:
            x1,y1,x2,y2 = mark["rect"]
            box = [x1-c["x"]+margin, y1-c["y"]+margin, x2-c["x"]+margin, y2-c["y"]+margin]
            if box[2]<=box[0] or box[3]<=box[1]:
                continue
            draw.rectangle(box, outline=color, width=3)
            cy=max(22,min(canvas.height-22,box[1]+16))
            while any(abs(cy-old)<44 for old in occupied):cy+=44
            cy=min(canvas.height-22,cy);occupied.append(cy)
            cx=box[0]-24 if mark.get('number_placement')=='before_target_in_column_gap' else 22
            center=(cx,cy)
            draw.ellipse((cx-18,cy-18,cx+18,cy+18),fill="white",outline=color,width=2)
            label=str(mark["number"])
            text_box=draw.textbbox((0,0),label,font=font)
            draw.text((center[0]-(text_box[2]-text_box[0])/2,cy-(text_box[3]-text_box[1])/2-text_box[1]),label,font=font,fill=color)
            end=(box[0],min(box[3],box[1]+16))
            arrow(draw,(cx+19,cy),end,color)
            marks.append({**mark,"output_rect":box,"number_center":center,"arrow_start":[cx+19,cy],"arrow_end":end})
        annotated=ASSETS/"annotated"/(ident+".png")
        canvas.save(annotated)
        config={"crop":bounds,"white_annotation_margin_px":margin,"marks":marks,"method":"Pillow deterministic crop and rectangle/arrow/number only; no generative image operation"}
        configurations[ident]=config
        entries.append({**source,"original_take_path":source["raw_path"],"original_take_public":False,"raw_path":raw.relative_to(ROOT).as_posix(),"raw_sha256":sha(raw),"annotated_path":annotated.relative_to(ROOT).as_posix(),"annotated_sha256":sha(annotated),"annotated_size":list(canvas.size),"annotation_config_key":ident})
    metadata={"release_version":"2.0.1","runtime_version":"2.0.0","created_at_utc":datetime.now(timezone.utc).isoformat(),"assurance":"Actual production UI capture. Only crop, white margin, numbered arrows and rectangles added. Source PNGs retained with hashes. No owner/cookie/active database is published.","takes":takes,"figures":entries}
    (ASSETS/"figure_index.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+"\n","utf8")
    (ASSETS/"annotation_config.json").write_text(json.dumps(configurations,ensure_ascii=False,indent=2)+"\n","utf8")
    (ASSETS/"capture_manifest.json").write_text(json.dumps({k:v for k,v in metadata.items() if k!="figures"}|{"figure_index":"docs/assets/core-features/figure_index.json","figure_count":len(entries)},ensure_ascii=False,indent=2)+"\n","utf8")
    print(json.dumps({"figures":len(entries),"index":"docs/assets/core-features/figure_index.json"}))


if __name__ == "__main__":
    main()
