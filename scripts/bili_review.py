#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复盘：把发布记录读成一张「哪种标题在我这个号上更有效」的报告。

用法:
    python bili_review.py                       # 读 profile/发布记录.csv
    python bili_review.py --csv 别的.csv
    python bili_review.py --since 2026-09-01

产出: profile/复盘-<最新一条的月份>.md，同时打印到终端。
样本少于 5 条时会明确说明「还看不出结论」，不要硬凑。
"""

import argparse
import csv
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

COLUMNS = ["日期", "标题", "题材", "钩子", "分区", "时长分钟",
           "播放", "点赞", "投币", "收藏", "评论", "粉丝增量"]


def num(value):
    if value is None:
        return 0
    text = re.sub(r"[,\s，]", "", str(value))
    m = re.match(r"^(-?\d+(?:\.\d+)?)(万|w|W)?$", text)
    if not m:
        return 0
    val = float(m.group(1))
    return val * 10000 if m.group(2) else val


def pct(a, b):
    return f"{a / b * 100:.1f}%" if b else "-"


def bucket(length):
    if length < 15:
        return "①<15字"
    if length <= 24:
        return "②15-24字"
    if length <= 34:
        return "③25-34字"
    return "④35字+"


def signals(title):
    out = []
    if re.search(r"\d", title):
        out.append("含数字")
    if "？" in title or "?" in title:
        out.append("含问号")
    if re.search(r"《.*?》", title):
        out.append("含作品名")
    if re.search(r"[你咱]", title):
        out.append("含你/咱")
    if any(w in title for w in ("为什么", "怎么", "如何")):
        out.append("疑问词")
    if any(w in title for w in ("其实", "根本", "真相", "骗", "错了", "代价")):
        out.append("反常识词")
    return out or ["无特征"]


def load(path):
    if not path.exists():
        sys.exit(f"找不到发布记录: {path}\n先按 references 里的表头建一个。")
    text = path.read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(text.splitlines()))
    clean = []
    for r in rows:
        title = (r.get("标题") or "").strip()
        if not title:
            continue
        r = {k: (r.get(k) or "").strip() for k in COLUMNS}
        play = num(r["播放"])
        if play <= 0:
            continue
        r["_play"] = play
        r["_like"] = num(r["点赞"])
        r["_coin"] = num(r["投币"])
        r["_fav"] = num(r["收藏"])
        r["_cmt"] = num(r["评论"])
        r["_triple"] = (r["_like"] + r["_coin"] + r["_fav"]) / play
        r["_cmt_rate"] = r["_cmt"] / play
        r["_signals"] = signals(title)
        clean.append(r)
    return clean


def med(rows, key):
    return statistics.median([r[key] for r in rows]) if rows else 0


def table(rows, group_key, label):
    groups = defaultdict(list)
    for r in rows:
        groups[group_key(r)].append(r)
    if len(groups) < 2:
        return []
    lines = [f"### 按{label}", "", "| 分组 | 条数 | 播放中位数 | 三连率中位数 |", "|---|---|---|---|"]
    ordered = sorted(groups.items(), key=lambda kv: -med(kv[1], "_triple"))
    for name, rs in ordered:
        lines.append(f"| {name} | {len(rs)} | {med(rs, '_play'):,.0f} | {pct(med(rs, '_triple'), 1)} |")
    lines.append("")
    return lines


def main():
    here = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="B 站发布记录复盘")
    ap.add_argument("--csv", default=str(here / "profile" / "发布记录.csv"))
    ap.add_argument("--since", help="只看这个日期之后的记录，如 2026-09-01")
    ap.add_argument("--out", help="报告输出路径，默认 profile/复盘-<月份>.md")
    args = ap.parse_args()

    rows = load(Path(args.csv))
    if args.since:
        rows = [r for r in rows if r["日期"] >= args.since]
    if not rows:
        sys.exit("没有可分析的记录（播放量为 0 或标题为空的行会被跳过）。")

    rows.sort(key=lambda r: r["日期"])
    months = sorted({r["日期"][:7] for r in rows if len(r["日期"]) >= 7})
    out = Path(args.out) if args.out else here / "profile" / f"复盘-{months[-1] if months else '全部'}.md"

    lines = [f"# 投稿复盘（{len(rows)} 条，截至 {rows[-1]['日期'] or '未知日期'}）", ""]
    lines += ["| 指标 | 中位数 | 最好的一条 |", "|---|---|---|"]
    best = max(rows, key=lambda r: r["_play"])
    lines += [
        f"| 播放 | {med(rows, '_play'):,.0f} | {best['_play']:,.0f}《{best['标题']}》 |",
        f"| 三连率 | {pct(med(rows, '_triple'), 1)} | {pct(max(r['_triple'] for r in rows), 1)} |",
        f"| 评论率 | {pct(med(rows, '_cmt_rate'), 1)} | {pct(max(r['_cmt_rate'] for r in rows), 1)} |",
        "",
    ]

    lines += ["## 播放前 5", "", "| 播放 | 三连率 | 标题 | 分区 |", "|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: -r["_play"])[:5]:
        lines.append(f"| {r['_play']:,.0f} | {pct(r['_triple'], 1)} | {r['标题']} | {r['分区']} |")
    lines += ["", "## 播放后 3", "", "| 播放 | 三连率 | 标题 | 分区 |", "|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["_play"])[:3]:
        lines.append(f"| {r['_play']:,.0f} | {pct(r['_triple'], 1)} | {r['标题']} | {r['分区']} |")
    lines.append("")

    lines += table(rows, lambda r: r["题材"] or "未填", "题材")
    lines += table(rows, lambda r: r["钩子"] or "未填", "钩子类型")
    lines += table(rows, lambda r: bucket(len(r["标题"])), "标题字数")
    lines += table(rows, lambda r: r["分区"] or "未填", "分区")

    by_signal = defaultdict(list)
    for r in rows:
        for s in r["_signals"]:
            by_signal[s].append(r)
    if len(by_signal) > 1:
        lines += ["### 按标题特征（一条标题可计入多组）", "", "| 特征 | 条数 | 播放中位数 | 三连率中位数 |", "|---|---|---|---|"]
        for name, rs in sorted(by_signal.items(), key=lambda kv: -med(kv[1], "_triple")):
            lines.append(f"| {name} | {len(rs)} | {med(rs, '_play'):,.0f} | {pct(med(rs, '_triple'), 1)} |")
        lines.append("")

    lines += ["## 怎么读这张表", ""]
    if len(rows) < 5:
        lines += [f"- 只有 {len(rows)} 条，样本太少，任何分组差异都可能是噪声。先按表继续记，攒到 10 条以上再看。"]
    else:
        lines += [
            "- 先看三连率，再看播放：播放受推送运气影响大，三连率更能说明标题和内容对不对得上。",
            "- 中位数比平均值稳，一条爆款会把平均值拉飞。",
            "- 某组条数 ≤ 2 时，结论只是线索，不是定论。",
        ]
    lines += [
        "- 结论写回 `references/title-patterns.md` 的「本号实测」一节，下次起标题优先用高分组。",
        "",
        f"数据文件：{Path(args.csv)}",
    ]

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n已写入 {out}")


if __name__ == "__main__":
    main()
