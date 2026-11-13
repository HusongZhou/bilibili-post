#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一个已下载的视频文件夹整理成「写投稿信息用的简报」。

用法:
    python bili_brief.py "E:\\Asset Library\\youtube\\<视频文件夹>"

产出（写在 <视频文件夹>/bili/ 下）:
    brief.md        元数据 + 章节 + 人物候选 + 时间轴锚点 + 候选钩子句
    transcript.txt  全文双语字幕，带时间码

只读原文件夹，不联网，不改动视频和字幕。
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".flv"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
CJK = re.compile(r"[\u4e00-\u9fff]")

# 钩子句打分用的信号词：出现频率高的说话人，往往是这类短视频里最抓人的位置
HOOK_WORDS = [
    "但是", "其实", "根本", "从不", "从来", "永远", "所有人", "没人", "没有人",
    "秘密", "真相", "关键", "问题在于", "代价", "错了", "骗", "失败", "第一次",
    "唯一", "秘诀", "为什么", "怎么", "如何", "结果", "发现", "直到", "突然",
    "最", "从不", "反而", "原来", "意识到", "承认", "害怕", "羞耻", "愤怒",
]

PROPER_STOP = {
    "i", "the", "a", "an", "and", "but", "so", "if", "it", "this", "that", "you",
    "he", "she", "we", "they", "my", "your", "his", "her", "our", "their", "what",
    "when", "where", "why", "how", "who", "not", "no", "yes", "just", "like",
    "well", "okay", "ok", "then", "there", "here", "now", "because", "cause",
    "actually", "really", "very", "much", "more", "most", "some", "any", "every",
    "all", "one", "two", "do", "does", "did", "is", "are", "was", "were", "be",
    "been", "have", "has", "had", "will", "would", "can", "could", "should",
    "get", "got", "go", "going", "know", "think", "want", "right", "yeah", "oh",
    "ah", "um", "uh", "mmm", "hey", "look", "see", "say", "said", "thing",
    "things", "people", "time", "way", "lot", "kind", "sort",
}


def human_duration(seconds):
    seconds = int(seconds or 0)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def stamp(seconds):
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def shorten(text, limit):
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def parse_timestamp(text):
    m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)", text) or re.search(r"(\d+):(\d+)[,.](\d+)", text)
    if not m:
        return None
    parts = [int(p) for p in m.groups()]
    if len(parts) == 4:
        h, mi, s, ms = parts
    else:
        h, (mi, s, ms) = 0, parts
    return h * 3600 + mi * 60 + s + ms / 1000


def clean_text(line):
    line = re.sub(r"<[^>]+>", "", line)
    line = re.sub(r"\{\\[^}]*\}", "", line)
    return line.replace("\u200b", "").strip()


def parse_srt(path):
    """返回 [(start, end, en, zh), ...]。双语字幕里中文那几行取第一个汉字之后的行。"""
    raw = path.read_text(encoding="utf-8-sig", errors="replace")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", raw.strip()):
        lines = [clean_text(l) for l in block.split("\n")]
        lines = [l for l in lines if l]
        if not lines:
            continue
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        start = parse_timestamp(lines[ti])
        end = parse_timestamp(lines[ti].split("-->")[1])
        body = lines[ti + 1:]
        if start is None or end is None or not body:
            continue
        zh_at = next((i for i, l in enumerate(body) if CJK.search(l)), None)
        if zh_at is None:
            en, zh = " ".join(body), ""
        else:
            en, zh = " ".join(body[:zh_at]), " ".join(body[zh_at:])
        cues.append((start, end, en, zh))
    return cues


def load_info(folder):
    for p in sorted(folder.glob("*.info.json")) + sorted(folder.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8-sig", errors="replace"))
        except Exception:
            continue
        if isinstance(data, dict) and ("title" in data or "uploader" in data):
            return data
    return {}


def pick(folder, exts, prefer=None, exclude=None):
    files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in exts]
    if exclude:
        files = [f for f in files if not re.search(exclude, f.stem, re.I)]
    if not files:
        return None
    if prefer:
        hit = [f for f in files if re.search(prefer, f.name, re.I)]
        if hit:
            files = hit
    return sorted(files, key=lambda f: (len(f.stem), -f.stat().st_size))[0]


def _capitalized(blob, counter):
    for m in re.finditer(r"[A-Z][A-Za-z'’\-]+(?:\s+[A-Z][A-Za-z'’\-]+)*", blob):
        phrase = m.group(0).strip()
        words = phrase.split()
        if words[0].lower() in PROPER_STOP:
            continue
        if len(phrase) < 3 or len(words) > 4:
            continue
        counter[phrase] += 1


def proper_nouns(cues, info, limit=15):
    """标题/简介里出现的一律保留；字幕里出现的只留重复 2 次以上的，避免自动字幕的错误词。"""
    head = Counter()
    _capitalized(" ".join([info.get("title", ""), (info.get("description") or "")[:2000]]), head)
    body = Counter()
    _capitalized(" ".join(c[2] for c in cues), body)
    out = [(k, v, "标题/简介") for k, v in head.most_common()]
    out += [(k, v, "字幕") for k, v in body.most_common() if v >= 2 and k not in head]
    return out[:limit]


def merge_segments(cues, max_cues=6, max_chars=110, max_gap=1.3):
    """字幕是按停顿切的，直接拿来当句子会断在半句上。合并成段再挑钩子。"""
    segs, buf = [], []

    def flush():
        if not buf:
            return
        en = " ".join(c[2] for c in buf if c[2]).strip()
        zh = "".join(c[3] for c in buf if c[3]).strip()
        segs.append((buf[0][0], buf[-1][1], en, zh))
        buf.clear()

    for i, cue in enumerate(cues):
        buf.append(cue)
        start, end, en, zh = cue
        gap = (cues[i + 1][0] - end) if i + 1 < len(cues) else 99
        done = (
            (zh and zh[-1] in "。！？…；")
            or (en and en[-1] in ".!?")
            or gap > max_gap
            or len(buf) >= max_cues
            or sum(len(c[3] or c[2]) for c in buf) >= max_chars
        )
        if done:
            flush()
    flush()
    return segs


NOISE = (
    "[音乐]", "[music]", "[applause]", "[掌声]", "[笑]", "[laughter]",
    "谢谢你们", "谢谢观看", "thanks for watching", "subscribe", "patreon",
    "字幕由", "字幕志愿者", "amara.org", "感谢收看",
)


def hook_candidates(segs, limit=12):
    scored = []
    seen = set()
    for start, end, en, zh in segs:
        if not zh or len(zh) < 8:
            continue
        blob = (zh + " " + en).lower()
        if any(n in blob for n in NOISE):
            continue
        key = zh[:10]
        if key in seen:
            continue
        score = 0
        if re.search(r"\d", zh):
            score += 2
        score += min(3, sum(1 for w in HOOK_WORDS if w in zh))
        if "？" in zh or "?" in zh:
            score += 1
        if 10 <= len(zh) <= 60:
            score += 1
        if score < 3:
            continue
        seen.add(key)
        scored.append((score, start, en, zh))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[:limit]


def timeline_anchors(segs, chunks=8):
    if not segs:
        return []
    total = segs[-1][1]
    if total <= 0:
        return []
    anchors = []
    for i in range(chunks):
        target = total * i / chunks
        seg = next((s for s in segs if s[0] >= target and s[3]), None)
        if seg and (not anchors or seg[3] != anchors[-1][1]):
            anchors.append((seg[0], shorten(seg[3], 60)))
    return anchors


def chapters_of(info):
    out = []
    for ch in info.get("chapters") or []:
        if isinstance(ch, dict) and ch.get("start_time") is not None:
            out.append((float(ch["start_time"]), ch.get("title") or ""))
    return out


def main():
    ap = argparse.ArgumentParser(description="把视频文件夹整理成 B 站投稿简报")
    ap.add_argument("path", help="视频文件夹（bilingual-sub 的输出目录）")
    ap.add_argument("--chunks", type=int, default=8, help="无章节时按几段切时间轴")
    args = ap.parse_args()

    folder = Path(args.path).expanduser()
    if folder.is_file():
        folder = folder.parent
    if not folder.is_dir():
        sys.exit(f"找不到文件夹: {folder}")

    video = pick(folder, VIDEO_EXT, exclude=r"_(bilingual|burned)$")
    cover = pick(folder, IMG_EXT, prefer=r"\.(jpg|jpeg|png|webp)$")
    srt = pick(folder, {".srt"}, prefer=r"bilingual")
    info = load_info(folder)

    if not srt:
        sys.exit(f"{folder.name}: 没有找到 .srt 字幕，先跑 bilingual-sub")
    cues = parse_srt(srt)
    if not cues:
        sys.exit(f"{srt.name}: 解析不出字幕内容")

    total = info.get("duration") or (cues[-1][1] if cues else 0)
    title = info.get("title") or (video.stem if video else folder.name)
    has_zh = any(c[3] for c in cues)
    segs = merge_segments(cues)

    out = folder / "bili"
    out.mkdir(exist_ok=True)

    # ---- brief.md ----
    n_chars = sum(len(c[3] or c[2]) for c in cues)
    lines = [f"# 简报：{title}", ""]
    rows = [
        ("原视频标题", title),
        ("频道 / 作者", info.get("uploader") or info.get("channel") or "（未知，可能需要手动补）"),
        ("发布日期", (info.get("upload_date") or "")[:8] or "未知"),
        ("时长", human_duration(total)),
        ("播放量", f"{info.get('view_count'):,}" if info.get("view_count") else "未知"),
        ("字幕", f"中英双语（{len(cues)} 条）" if has_zh else f"仅英文（{len(cues)} 条），中文需自行理解"),
        ("字幕密度", f"{len(cues) / max(1, total / 60):.1f} 条/分钟，共约 {n_chars} 字"),
        ("视频文件", video.name if video else "未找到"),
        ("封面文件", cover.name if cover else "未找到"),
        ("原链接", info.get("webpage_url") or "未知"),
    ]
    lines += ["| 项 | 值 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]
    lines.append("")

    desc = (info.get("description") or "").strip()
    if desc:
        lines += ["## 原视频简介（作者原文）", "", desc[:1500], ""]

    chaps = chapters_of(info)
    if chaps:
        lines += ["## 原视频章节", ""]
        lines += [f"- `{stamp(start)}` {name}" for start, name in chaps]
        lines.append("")

    tags = info.get("tags") or []
    if tags:
        lines += ["## 原视频标签（作者自填）", "", "、".join(map(str, tags[:30])), ""]

    pn = proper_nouns(cues, info)
    lines += ["## 人物 / 专有名词候选", ""]
    if pn:
        lines += [f"- {name} ×{n}（{src}）" for name, n, src in pn]
    else:
        lines.append("- 没抓到（自动字幕常全小写），人名和作品名请从标题、简介里确认")
    lines.append("")

    anchors = timeline_anchors(segs, max(3, args.chunks))
    if anchors:
        lines += ["## 时间轴锚点（按字幕均分，仅供起草用，正式章节要按内容重排）", ""]
        lines += [f"| {stamp(t)} | {text} |" for t, text in anchors]
        lines.append("")

    hooks = hook_candidates(segs)
    lines += ["## 候选钩子段（连续字幕合并，按信号强度排序）", ""]
    for i, (score, start, en, zh) in enumerate(hooks, 1):
        lines.append(f"{i}. `{stamp(start)}` **{shorten(zh, 90)}**")
        if en and en.lower() != zh.lower():
            lines.append(f"   > {shorten(en, 140)}")
    lines.append("")
    lines += [
        "## 提示",
        "",
        "- 双语字幕的中文是机翻，人名、术语、梗都可能错；引用金句前对照上面的英文原文。",
        "- 候选钩子段只是原料，标题要自己提炼；口语直接抄上去会显得散。"
    ]

    (out / "brief.md").write_text("\n".join(lines), encoding="utf-8")

    # ---- transcript.txt ----
    tlines = [f"# {title}  ({human_duration(total)})", ""]
    for start, end, en, zh in cues:
        if zh and en:
            tlines.append(f"[{stamp(start)}] {zh}  ||  {en}")
        else:
            tlines.append(f"[{stamp(start)}] {zh or en}")
    (out / "transcript.txt").write_text("\n".join(tlines), encoding="utf-8")

    print(f"brief:      {out / 'brief.md'}")
    print(f"transcript: {out / 'transcript.txt'}")
    print(f"视频: {title} | {human_duration(total)} | {len(cues)} 条字幕 | 钩子 {len(hooks)} 条")


if __name__ == "__main__":
    main()
