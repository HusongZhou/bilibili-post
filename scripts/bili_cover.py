#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把原视频封面改成 B 站 16:10，并用中文钩子盖掉原封面上的外文标题。

用法:
    python bili_cover.py "E:\\Asset Library\\youtube\\<视频文件夹>" --hook "它被低估了" --label "《足球教练》"

    # 一次出多版
    python bili_cover.py "<文件夹>" --hooks "它被低估了|不是爽剧|拍对了三件事"

产出: <视频文件夹>/bili/封面/<钩子>.jpg

为什么是「盖」不是「抠」：原封面上的外文大字往往带投影，逐像素修补会留下灰边；
用一块整色面板压上去，边缘做渐变，既干净又像刻意设计。
"""

import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

W, H = 1920, 1200
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
PANEL_COLOR = (11, 22, 38)
TEXT_COLOR = (255, 255, 255)
LABEL_COLOR = (236, 196, 92)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]


def pick_font_path():
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    sys.exit("找不到中文字体，用 --font 指定一个 .ttf/.ttc")


def find_cover(path):
    p = Path(path).expanduser()
    if p.is_file():
        return p
    if not p.is_dir():
        sys.exit(f"找不到路径: {p}")
    imgs = [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in IMG_EXT]
    if not imgs:
        sys.exit(f"{p.name}: 文件夹里没有封面图")
    # 优先取和视频同名的
    videos = [f.stem for f in p.iterdir() if f.suffix.lower() in {".mp4", ".mkv", ".webm"}]
    for stem in videos:
        for f in imgs:
            if f.stem == stem:
                return f
    return sorted(imgs, key=lambda f: -f.stat().st_size)[0]


def to_canvas(img, anchor="center"):
    """等比铺满 1920x1200，多余部分裁掉。"""
    scale = max(W / img.width, H / img.height)
    big = img.resize((max(W, int(round(img.width * scale))), max(H, int(round(img.height * scale)))), Image.LANCZOS)
    if anchor == "left":
        left = 0
    elif anchor == "right":
        left = big.width - W
    else:
        left = (big.width - W) // 2
    top = (big.height - H) // 2
    return big.crop((left, top, left + W, top + H)).convert("RGB")


def text_mass(canvas):
    """比较左右两侧的硬边缘密度，边缘更密的一侧通常压着原封面的外文标题。

    只比左右：竖切面板在 16:10 上永远构成立，上下横条容易被人物挡住，
    留给人自己用 --panel 指定。
    """
    small = canvas.convert("L").resize((240, 150), Image.LANCZOS)
    edges = small.filter(ImageFilter.FIND_EDGES)
    zones = {"left": (0, 0, 96, 150), "right": (144, 0, 240, 150)}
    scores = {k: ImageStat.Stat(edges.crop(b)).mean[0] for k, b in zones.items()}
    return max(scores, key=scores.get), scores


def panel_geometry(side):
    """返回 (实色区宽或高, 渐变结束位置)，单位像素。"""
    if side in ("left", "right"):
        return int(W * 0.40), int(W * 0.62)
    return int(H * 0.34), int(H * 0.50)


def panel_mask(side):
    """整色面板的不透明度：先全不透明，再平滑过渡到透明。"""
    solid, fade_end = panel_geometry(side)
    mask = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(mask)
    if side in ("left", "right"):
        for x in range(solid, fade_end):
            t = (x - solid) / max(1, fade_end - solid)
            a = int(255 * (1 - t * t * (3 - 2 * t)))
            px = x if side == "left" else W - 1 - x
            draw.line([(px, 0), (px, H)], fill=a)
        if side == "left":
            draw.rectangle([0, 0, solid, H], fill=255)
        else:
            draw.rectangle([W - solid, 0, W, H], fill=255)
    else:
        span = max(1, fade_end - solid)
        if side == "bottom":
            draw.rectangle([0, H - solid, W, H], fill=255)
            for y in range(H - fade_end, H - solid):
                t = (y - (H - fade_end)) / span
                draw.line([(0, y), (W, y)], fill=int(255 * (t * t * (3 - 2 * t))))
        else:
            draw.rectangle([0, 0, W, solid], fill=255)
            for y in range(solid, fade_end):
                t = (y - solid) / span
                draw.line([(0, y), (W, y)], fill=int(255 * (1 - t * t * (3 - 2 * t))))
    return mask


def fit_font(draw, text, max_width, start, font_path):
    size = start
    while size > 36:
        f = ImageFont.truetype(font_path, size)
        if draw.textlength(text, font=f) <= max_width:
            return f
        size -= 4
    return ImageFont.truetype(font_path, 36)


def render(canvas, hook, label, side, font_path):
    overlay = Image.new("RGB", (W, H), PANEL_COLOR)
    canvas = Image.composite(overlay, canvas, panel_mask(side))
    draw = ImageDraw.Draw(canvas)

    solid, _ = panel_geometry(side)
    margin = int(W * 0.06)
    if side in ("left", "right"):
        # 允许文字压到渐变区上：缩略图里字大一点更抓人
        max_w = int(W * 0.54) - margin
        x = margin if side == "left" else W - margin - max_w
    else:
        max_w = W - margin * 2
        x = margin

    f_hook = fit_font(draw, hook, max_w, 190, font_path)
    f_label = fit_font(draw, label, max_w, 58, font_path) if label else None

    hook_h = f_hook.size + 14
    gap = 42
    block = hook_h + (gap + f_label.size if f_label else 0)

    if side in ("left", "right"):
        top = (H - block) // 2
    elif side == "bottom":
        top = H - solid + max(0, (solid - block) // 2)
    else:
        top = max(0, (solid - block) // 2)

    bar_x = x - 44
    draw.rectangle([bar_x, top + 6, bar_x + 7, top + block - 6], fill=LABEL_COLOR)

    draw.text((x + 3, top + 5), hook, font=f_hook, fill=(0, 0, 0, 130))
    draw.text((x, top), hook, font=f_hook, fill=TEXT_COLOR)
    if f_label:
        draw.text((x, top + hook_h + gap), label, font=f_label, fill=LABEL_COLOR)
    return canvas


def main():
    ap = argparse.ArgumentParser(description="原视频封面 → B 站 16:10 封面")
    ap.add_argument("path", help="视频文件夹，或直接指定封面图")
    ap.add_argument("--hook", action="append", default=[], help="封面文案，可重复")
    ap.add_argument("--hooks", help="一次多个，用 | 分隔")
    ap.add_argument("--label", default="", help="下面的小字，通常是《剧名》")
    ap.add_argument("--panel", default="left", choices=["auto", "left", "right", "top", "bottom"])
    ap.add_argument("--anchor", default="auto", choices=["auto", "center", "left", "right"], help="裁切时保留哪一侧")
    ap.add_argument("--font", default="", help="中文字体路径")
    ap.add_argument("--out", default="", help="输出目录，默认 <视频文件夹>/bili/封面")
    args = ap.parse_args()

    hooks = list(args.hook)
    if args.hooks:
        hooks += [h.strip() for h in args.hooks.split("|") if h.strip()]
    if not hooks:
        sys.exit('至少给一个封面文案：--hook "它被低估了"')

    src = find_cover(args.path)
    font_path = args.font or pick_font_path()
    src_img = Image.open(src)

    side = args.panel
    if side == "auto":
        side, scores = text_mass(to_canvas(src_img, "center"))
        print("边缘密度 " + " ".join(f"{k}={v:.1f}" for k, v in scores.items()) + f" -> 面板放 {side}")
    else:
        print(f"面板放 {side}")

    # 面板在哪边，就从哪边裁：把原文字裁掉一部分，同时保住另一侧的人物
    anchor = args.anchor
    if anchor == "auto":
        anchor = {"left": "right", "right": "left"}.get(side, "center")
    canvas = to_canvas(src_img, anchor)

    out_dir = Path(args.out) if args.out else (src.parent / "bili" / "封面")
    out_dir.mkdir(parents=True, exist_ok=True)

    for hook in hooks:
        img = render(canvas.copy(), hook, args.label, side, font_path)
        safe = re.sub(r'[\\/:*?"<>|｜]', "", hook)[:24] or "cover"
        dst = out_dir / f"{safe}.jpg"
        img.save(dst, quality=94, subsampling=0)
        print(dst)


if __name__ == "__main__":
    main()
